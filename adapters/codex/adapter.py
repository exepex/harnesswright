"""Eval adapter for the OpenAI Codex command line in non-interactive mode (`codex exec`).

Codex discovers skills in `.agents/skills/` and reads a skill by opening its SKILL.md with a
shell command, so a skill counts as triggered when a command in the JSON event stream opens that
file, or a tool call's arguments name it.
"""

import json
import re
import shlex
from pathlib import Path

NAME = "codex"
CLI = "codex"
# Commands that can name a file without reading its content. Any other command that names
# SKILL.md (cat, sed, rg, grep, python, ...) counts as reading it.
PATH_ONLY_COMMANDS = ("ls", "find", "fd", "tree", "stat", "test", "[", "file", "du", "realpath",
                      "readlink", "dirname", "basename", "echo", "printf", "touch", "mkdir", "cd")
# Flags that turn a reading command into a path-only one, such as `rg --files`, which lists files
# "without actually performing the search".
PATH_ONLY_FLAGS = {"rg": ("--files",)}
# Flags that make a path-only command run another command on the file, such as `find ... -exec cat {} ;`.
RUNS_COMMAND_FLAGS = {"find": ("-exec", "-execdir", "-ok", "-okdir"), "fd": ("-x", "--exec", "-X", "--exec-batch")}
SHELLS = ("bash", "sh", "zsh", "dash")


def skill_dir(workspace, skill_name):
    """Repository-level skills folder that Codex discovers."""
    return Path(workspace) / ".agents" / "skills" / skill_name


def build_command(mode, workspace, model, scratch=None):
    """Command for one run. The trailing '-' makes Codex read the prompt from stdin.

    `scratch` is a writable folder outside the workspace for tool caches, given only to task runs.
    """
    if mode not in ("trigger", "task"):
        raise ValueError(f"unknown mode: {mode}")
    sandbox = "read-only" if mode == "trigger" else "workspace-write"
    command = [CLI, "exec", "--json", "--ephemeral", "--skip-git-repo-check",
               "--sandbox", sandbox, "--cd", str(workspace)]
    if mode == "task" and scratch:
        command += ["--add-dir", str(scratch)]
    if model:
        command += ["--model", model]
    return command + ["-"]


def missing_requirements(mode):
    """Codex brings its own sandbox, so nothing else is needed."""
    return None


def permission_profile(mode):
    """What a run in this mode may do, recorded with every result."""
    if mode == "trigger":
        return {"reads": "any", "commands": "allowed, sandboxed", "writes": "refused",
                "setting": "sandbox read-only"}
    return {"reads": "any", "commands": "allowed, sandboxed", "writes": "workspace, scratch and /tmp",
            "network": "blocked", "setting": "sandbox workspace-write"}


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


def _split(text):
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _segments(command):
    """The simple commands in a command line, with a `bash -lc '...'` wrapper unwrapped."""
    words = _split(command)
    if words and words[0].rsplit("/", 1)[-1] in SHELLS:
        for index, word in enumerate(words[1:-1], start=1):
            if word.startswith("-") and "c" in word:
                return _segments(words[index + 1])
    return [part for part in re.split(r"&&|\|\||[;|\n]", command) if part.strip()]


def _program(segment):
    for word in _split(segment):
        if "=" in word.split("/", 1)[0] or word in ("sudo", "env", "command", "exec", "time", "("):
            continue
        return word.rsplit("/", 1)[-1].lower()
    return ""


def _path_only(segment):
    program = _program(segment)
    if any(flag in _split(segment) for flag in RUNS_COMMAND_FLAGS.get(program, ())):
        return False
    if program in PATH_ONLY_COMMANDS:
        return True
    return any(flag in _split(segment) for flag in PATH_ONLY_FLAGS.get(program, ()))


def _reads_file(command, marker):
    """True when a simple command that names the path can read it. Output is never inspected."""
    if marker not in command:
        return False
    return any(marker in segment and not _path_only(segment) for segment in _segments(command))


def skill_triggered(events, skill_name):
    """True when Codex ran a command that reads the skill's SKILL.md, or a tool call whose arguments name it."""
    marker = f"skills/{skill_name}/SKILL.md"
    for item in _items(events):
        if item.get("type") == "command_execution" and _reads_file(str(item.get("command", "")), marker):
            return True
        if item.get("type") == "mcp_tool_call" and marker in json.dumps(item.get("arguments", {})):
            return True
    return False


def refusals(events):
    """Actions the host refused. `codex exec` never asks for approval: a command the sandbox blocks
    fails and the model sees the error, as on any host, so there is nothing to refuse."""
    return []


def resolved_model(events):
    """The model the host used, when an event reports it. codex-cli 0.166.0 does not."""
    for event in events:
        if isinstance(event.get("model"), str) and event["model"]:
            return event["model"]
    return None


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
