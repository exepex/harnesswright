"""Eval adapter for the OpenAI Codex command line in non-interactive mode (`codex exec`).

Codex discovers skills in `.agents/skills/` and reads a skill by opening its SKILL.md, so a
skill counts as triggered when a command or tool call in the JSON event stream names that file.
"""

import json
from pathlib import Path

NAME = "codex"
CLI = "codex"
# Commands that print a file. Listing or searching commands can show a path without reading it.
READ_COMMANDS = ("cat", "sed", "head", "tail", "less", "more", "nl", "awk", "bat", "type", "get-content")


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


def _reads_file(command, marker):
    """True when a shell command runs a file-printing command on the path. Output is never inspected."""
    if marker not in command:
        return False
    words = command.replace("'", " ").replace('"', " ").replace(";", " ").replace("|", " ").split()
    return any(word.rsplit("/", 1)[-1].lower() in READ_COMMANDS for word in words)


def skill_triggered(events, skill_name):
    """True when Codex ran a command that reads the skill's SKILL.md, or a tool call whose arguments name it."""
    marker = f"skills/{skill_name}/SKILL.md"
    for item in _items(events):
        if item.get("type") == "command_execution" and _reads_file(str(item.get("command", "")), marker):
            return True
        if item.get("type") == "mcp_tool_call" and marker in json.dumps(item.get("arguments", {})):
            return True
    return False


def final_message(events):
    text = ""
    for item in _items(events):
        if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            text = item["text"]
    return text


def failure(events, returncode, timed_out, mode):
    """Return why the run failed, or None.

    A timed-out task run always fails: partial work is not a finished task. A timed-out trigger run
    counts when items already arrived, because the trigger decision comes first.
    """
    for event in events:
        if event.get("type") in ("turn.failed", "error"):
            detail = event.get("error") or event.get("message") or ""
            if isinstance(detail, dict):
                detail = detail.get("message", "")
            return f"host reported {event['type']}: {detail}".rstrip(": ")
    if timed_out:
        if mode == "trigger" and any(True for _ in _items(events)):
            return None
        return "timed out"
    if returncode not in (0, None):
        return f"exit code {returncode}"
    if not any(e.get("type") == "turn.completed" for e in events):
        return "no turn.completed event"
    return None
