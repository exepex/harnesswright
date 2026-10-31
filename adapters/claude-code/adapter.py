"""Eval adapter for Claude Code, the reference host.

Runs `claude -p` with the prompt on stdin and reads its stream-json events. A skill counts as
triggered when the host calls its Skill tool with the skill's name, or reads the skill's SKILL.md.
"""

import hashlib
import json
import re
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


# The eval harness contract (evals/harness/host.py). The jail enforces the power table, so permission checks are
# off, and the host gets only the tools below and the skills the case installs: its bundled skills, its built-in
# plugins and the two skills that survive the bundled-skill switch are turned off.
TOOLS = {"Bash": "command", "Read": "read", "Write": "write", "Edit": "write", "Glob": "read", "Grep": "read",
         "Skill": "skill", "Task": "agent"}
JAIL_SETTINGS = {"disableBundledSkills": True, "skillOverrides": {"design": "off", "doctor": "off"},
                 "enabledPlugins": {"cc-plugin-agents-md@builtin": False, "cc-plugin-telemetry@builtin": False,
                                    "cc-plugin-plugin-authoring@builtin": False}}
# Claude Code refuses to skip permissions as root unless told it runs in a sandbox, which the jail is.
RUN_ENV = {"IS_SANDBOX": "1"}
EXIT_CODE = re.compile(r"^Exit code (\d+)")
SKILL_FILE = re.compile(r"skills/([^/]+)/SKILL\.md$")


def jail_command(mode, world, model):
    command = [CLI, "-p", "--output-format", "stream-json", "--verbose", "--setting-sources", "project",
               "--no-session-persistence", "--dangerously-skip-permissions", "--settings", json.dumps(JAIL_SETTINGS),
               "--tools", ",".join(TOOLS)]
    return command + (["--model", model] if model else [])


def _result_text(content):
    if isinstance(content, list):
        return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return str(content or "")


def action_log(stdout, home):
    """Tool calls in order, each with its result; sub-agents' calls come in the same stream. A call with no result
    never finished, as when the stream is cut, so it is left out."""
    events, log = parse_events(stdout), []
    results = {item.get("tool_use_id"): item for event in events if event.get("type") == "user"
               for item in (event.get("message") or {}).get("content") or []
               if isinstance(item, dict) and item.get("type") == "tool_result"}
    for event in events:
        for item in (event.get("message") or {}).get("content") or [] if event.get("type") == "assistant" else []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                log.append({"kind": "message", "source": "observed", "text": str(item.get("text", ""))})
            elif item.get("type") == "tool_use" and item.get("id") in results:
                log += _tool_entries(item.get("name"), item.get("input") or {}, results[item.get("id")])
    for event in events:
        for denial in event.get("permission_denials") or [] if event.get("type") == "result" else []:
            if isinstance(denial, dict):
                log.append({"kind": "blocked", "source": "observed", "action": str(denial.get("tool_name", "")),
                            "reason": "the host refused it"})
    return log


def _tool_entries(name, tool_input, result):
    path, failed = str(tool_input.get("file_path") or tool_input.get("path") or "."), bool(result.get("is_error"))
    text = _result_text(result.get("content"))
    if name in ("Write", "Edit") and failed:
        return [{"kind": "failed", "source": "observed", "action": f"{name}: {path}", "path": path, "reason": text}]
    if failed and name != "Bash":
        return []
    if name == "Read" or name == "Grep":
        found = SKILL_FILE.search(path) if name == "Read" else None  # reading a skill's SKILL.md loads it
        return [{"kind": "read", "source": "observed", "path": path}] + (
            [{"kind": "skill", "source": "inferred", "name": found.group(1)}] if found else [])
    if name == "Write":
        content = str(tool_input.get("content", ""))
        return [{"kind": "write", "source": "observed", "path": path,
                 "sha256": hashlib.sha256(content.encode()).hexdigest()}]
    if name == "Edit":
        return [{"kind": "write", "source": "observed", "path": path, "sha256": None}]
    if name == "Bash":
        code = EXIT_CODE.match(text) if failed else None  # only an error result starts with its exit code
        return [{"kind": "command", "source": "observed", "command": str(tool_input.get("command", "")),
                 "exit_code": int(code.group(1)) if code else (None if failed else 0), "output": text[:4000]}]
    if name == "Skill":
        return [{"kind": "skill", "source": "observed", "name": str(tool_input.get("skill", "")).split(":")[-1]}]
    if name == "Task":
        return [{"kind": "agent", "source": "observed",
                 "task": str(tool_input.get("description") or tool_input.get("prompt") or "")}]
    return []  # Glob lists names and reads no file


def exposure(stdout, home):
    """The skills and tools of the start-up event; None when it does not list both, as no report is never
    'nothing'."""
    for event in parse_events(stdout):
        if event.get("type") == "system" and event.get("subtype") == "init":
            skills, tools = event.get("skills"), event.get("tools")
            return {"skills": list(skills), "tools": list(tools)} if isinstance(skills, list) and isinstance(
                tools, list) else None
    return None


def run_failure(stdout, returncode, timed_out):
    return failure(parse_events(stdout), returncode, timed_out, "task")
