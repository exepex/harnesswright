"""Eval adapter for Claude Code, the reference host.

Runs `claude -p` with the prompt on stdin and reads its stream-json events. A skill counts as
triggered when the host calls its Skill tool with the skill's name, or reads the skill's SKILL.md.
"""

import json
import shutil
import sys
from pathlib import Path

NAME = "claude-code"
CLI = "claude"
# What a sealed run passes on to sign in: these variables, and copies of these files from the real home.
ENV_KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN")
CREDENTIAL_FILES = (".claude/.credentials.json",)
# The model host the eval gate allows.
MODEL_HOSTS = ("api.anthropic.com",)
# Task runs: commands run in the host's sandbox, which allows writes only inside the workspace and the
# scratch folder and blocks the network, so they are approved without a prompt. The same powers as
# Codex's workspace-write sandbox. Commands that cannot run in the sandbox are refused, never run outside it.
# The sandbox's own auto-approval still asks about some compound commands (`cd x; a; b`, heredocs), so the
# command tool is allowed too; every command it runs stays inside the sandbox.
TASK_SETTINGS = {"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True,
                             "allowUnsandboxedCommands": False}}
# The sandbox needs these on Linux; without them Claude Code turns it off and refuses every command.
LINUX_SANDBOX_TOOLS = ("bwrap", "socat")


def skill_dir(workspace, skill_name):
    """Project-level skills folder that Claude Code discovers."""
    return Path(workspace) / ".claude" / "skills" / skill_name


def build_command(mode, workspace, model, scratch=None):
    """Command for one non-interactive run. The prompt goes on stdin; cwd is the workspace.

    `scratch` is a writable folder outside the workspace for tool caches, given only to task runs.
    """
    if mode not in ("trigger", "task"):
        raise ValueError(f"unknown mode: {mode}")
    command = [CLI, "-p", "--output-format", "stream-json", "--verbose",
               "--setting-sources", "project", "--no-session-persistence"]
    if mode == "task":
        command += ["--permission-mode", "acceptEdits", "--settings", json.dumps(TASK_SETTINGS),
                    "--allowedTools", "Bash"]
        if scratch:
            command += ["--add-dir", str(scratch)]
    if model:
        command += ["--model", model]
    return command


def missing_requirements(mode, platform=sys.platform):
    """Why this host cannot give a task run its full powers here, or None."""
    if mode != "task" or not platform.startswith("linux"):
        return None
    missing = [tool for tool in LINUX_SANDBOX_TOOLS if shutil.which(tool) is None]
    if missing:
        return f"the Claude Code sandbox needs {', '.join(missing)} on PATH"
    return None


def permission_profile(mode):
    """What a run in this mode may do, recorded with every result."""
    if mode == "trigger":
        return {"reads": "workspace", "commands": "refused", "writes": "refused",
                "setting": "default permission mode, no one to approve"}
    return {"reads": "any", "commands": "allowed, sandboxed", "writes": "workspace and scratch",
            "network": "blocked", "setting": "acceptEdits, sandbox on, unsandboxed commands refused"}


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


# A host safety check (such as `rm -rf $VAR`) that no permission setting can lift says so in its message.
# It is the host's own behaviour, the same for every user, not a lack of powers, so it is not a refusal.
SAFETY_CHECK = "cannot be auto-allowed by permission rules"


def _safety_checks(events):
    ids = set()
    for event in events:
        if event.get("type") != "user":
            continue
        for item in (event.get("message") or {}).get("content") or []:
            if isinstance(item, dict) and item.get("type") == "tool_result" and SAFETY_CHECK in str(item.get("content")):
                ids.add(item.get("tool_use_id"))
    return ids


def refusals(events):
    """Actions the host refused to run because they needed approval no one could give.

    Host safety checks that no setting can lift are left out (see SAFETY_CHECK).
    """
    found, safety = [], _safety_checks(events)
    for event in events:
        if event.get("type") != "result":
            continue
        for denial in event.get("permission_denials") or []:
            if isinstance(denial, dict) and denial.get("tool_use_id") not in safety:
                tool_input = denial.get("tool_input") or {}
                detail = tool_input.get("command") or tool_input.get("file_path") or ""
                found.append(f"{denial.get('tool_name', 'tool')}: {detail}".rstrip(": "))
    return found


def resolved_model(events):
    """The model the host actually used, from its init event."""
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init" and event.get("model"):
            return str(event["model"])
    return None


def final_message(events):
    for event in reversed(events):
        if event.get("type") == "result" and isinstance(event.get("result"), str):
            return event["result"]
    return ""


def failure(events, returncode, timed_out, mode):
    """Return why the run failed, or None.

    A timed-out task run always fails: partial work is not a finished task. A timed-out trigger run
    counts when the host already acted, because the trigger decision comes first.
    """
    for event in events:
        if event.get("type") == "result" and event.get("is_error"):
            return f"host reported an error: {event.get('subtype', 'error')}"
    if timed_out:
        if mode == "trigger" and any(e.get("type") == "assistant" for e in events):
            return None
        return "timed out"
    if returncode not in (0, None):
        return f"exit code {returncode}"
    if not any(e.get("type") == "result" for e in events):
        return "no result event"
    return None
