"""Eval adapter for Claude Code, the reference host.

Runs `claude -p` with the prompt on stdin and reads its stream-json events. A skill counts as
triggered when the host calls its Skill tool with the skill's name, or reads the skill's SKILL.md.
"""

import json
from pathlib import Path

NAME = "claude-code"
CLI = "claude"


def skill_dir(workspace, skill_name):
    """Project-level skills folder that Claude Code discovers."""
    return Path(workspace) / ".claude" / "skills" / skill_name


def build_command(mode, workspace, model):
    """Command for one non-interactive run. The prompt goes on stdin; cwd is the workspace."""
    if mode not in ("trigger", "task"):
        raise ValueError(f"unknown mode: {mode}")
    command = [CLI, "-p", "--output-format", "stream-json", "--verbose",
               "--setting-sources", "project", "--no-session-persistence"]
    if mode == "task":
        # Edits inside the workspace are allowed; anything else is refused, never approved silently.
        command += ["--permission-mode", "acceptEdits"]
    if model:
        command += ["--model", model]
    return command


def environment(env):
    """Drop the variable that marks a running session, so a nested run is allowed."""
    return {key: value for key, value in env.items() if key != "CLAUDECODE"}


def parse_events(stdout):
    events = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _tool_uses(events):
    for event in events:
        if event.get("type") != "assistant":
            continue
        for item in event.get("message", {}).get("content", []) or []:
            if isinstance(item, dict) and item.get("type") == "tool_use":
                yield item.get("name", ""), item.get("input") or {}


def skill_triggered(events, skill_name):
    marker = f"skills/{skill_name}/SKILL.md"
    for name, tool_input in _tool_uses(events):
        if name == "Skill" and tool_input.get("skill") in (skill_name, f"{skill_name}:{skill_name}"):
            return True
        if name == "Read" and str(tool_input.get("file_path", "")).endswith(marker):
            return True
    return False


def final_message(events):
    for event in reversed(events):
        if event.get("type") == "result" and isinstance(event.get("result"), str):
            return event["result"]
    return ""


def failure(events, returncode, timed_out):
    """Return why the run failed, or None. A timed-out run still counts if events arrived."""
    for event in events:
        if event.get("type") == "result" and event.get("is_error"):
            return f"host reported an error: {event.get('subtype', 'error')}"
    if timed_out:
        return None if any(e.get("type") == "assistant" for e in events) else "timed out with no output"
    if returncode not in (0, None):
        return f"exit code {returncode}"
    if not any(e.get("type") == "result" for e in events):
        return "no result event"
    return None
