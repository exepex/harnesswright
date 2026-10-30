"""Eval adapter for the OpenAI Codex command line in non-interactive mode (`codex exec`).

Codex discovers skills in `.agents/skills/` and reads a skill by opening its SKILL.md, so a
skill counts as triggered when a command or tool call in the JSON event stream names that file.
"""

import json
from pathlib import Path

NAME = "codex"
CLI = "codex"
READ_ITEM_TYPES = ("command_execution", "mcp_tool_call")


def skill_dir(workspace, skill_name):
    """Repository-level skills folder that Codex discovers."""
    return Path(workspace) / ".agents" / "skills" / skill_name


def build_command(mode, workspace, model):
    """Command for one run. The trailing '-' makes Codex read the prompt from stdin."""
    if mode not in ("trigger", "task"):
        raise ValueError(f"unknown mode: {mode}")
    sandbox = "read-only" if mode == "trigger" else "workspace-write"
    command = [CLI, "exec", "--json", "--ephemeral", "--skip-git-repo-check",
               "--sandbox", sandbox, "--cd", str(workspace)]
    if model:
        command += ["--model", model]
    return command + ["-"]


def environment(env):
    return dict(env)


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


def _items(events):
    for event in events:
        if str(event.get("type", "")).startswith("item.") and isinstance(event.get("item"), dict):
            yield event["item"]


def skill_triggered(events, skill_name):
    marker = f"skills/{skill_name}/SKILL.md"
    for item in _items(events):
        if item.get("type") in READ_ITEM_TYPES and marker in json.dumps(item):
            return True
    return False


def final_message(events):
    text = ""
    for item in _items(events):
        if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            text = item["text"]
    return text


def failure(events, returncode, timed_out):
    """Return why the run failed, or None. A timed-out run still counts if items arrived."""
    for event in events:
        if event.get("type") in ("turn.failed", "error"):
            detail = event.get("error") or event.get("message") or ""
            if isinstance(detail, dict):
                detail = detail.get("message", "")
            return f"host reported {event['type']}: {detail}".rstrip(": ")
    if timed_out:
        return None if any(True for _ in _items(events)) else "timed out with no output"
    if returncode not in (0, None):
        return f"exit code {returncode}"
    if not any(e.get("type") == "turn.completed" for e in events):
        return "no turn.completed event"
    return None
