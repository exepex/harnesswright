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


# ---- Eval harness contract (doc 11). The functions above serve the phase 2 runner until it is removed. ----

# Skills Claude Code 2.1.316 still lists with bundled skills and built-in plugins turned off. They are the same in
# both arms, and the judges approve this list as part of the measuring kit.
HOST_SKILLS = ("design", "doctor")
# Built-in plugins of Claude Code 2.1.316, turned off by name.
BUILTIN_PLUGINS = ("cc-plugin-agents-md@builtin", "cc-plugin-telemetry@builtin", "cc-plugin-plugin-authoring@builtin")
SEALED_ENV = {"CLAUDE_CODE_DISABLE_BUNDLED_SKILLS": "1"}
# The tools of the power table: read and search files, write them (task runs), run commands, load skills.
TOOLS = {"trigger": ("Bash", "Read", "Glob", "Grep", "Skill"),
         "task": ("Bash", "Read", "Glob", "Grep", "Skill", "Edit", "Write")}
READ_TOOLS = {"Read": "file_path", "NotebookRead": "notebook_path"}
SEARCH_TOOLS = ("Glob", "Grep")
WRITE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
OUTPUT_LIMIT = 4000


def settings(deny=()):
    """Run settings: the sandbox confines every command, bundled skills and built-in plugins are off, and each
    denied command prefix is refused."""
    value = {"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True, "allowUnsandboxedCommands": False},
             "disableBundledSkills": True, "enabledPlugins": {name: False for name in BUILTIN_PLUGINS}}
    if deny:
        value["permissions"] = {"deny": [f"Bash({prefix}:*)" for prefix in deny]}
    return value


def command(mode, world, scratch=None, model=None, deny=()):
    """The `claude -p` command for one harness run, configured to the power table.

    Commands run in the host's sandbox in both modes, which lets them write only the working folder and the
    added scratch folder. In a trigger run the jail mounts the world read-only and no folder is added, so
    commands can write nowhere.
    """
    if mode not in ("trigger", "task"):
        raise ValueError(f"unknown mode: {mode}")
    args = [CLI, "-p", "--output-format", "stream-json", "--verbose", "--setting-sources", "project",
            "--no-session-persistence", "--strict-mcp-config", "--tools", ",".join(TOOLS[mode]),
            "--settings", json.dumps(settings(deny)), "--allowedTools", "Bash"]
    if mode == "task":
        args += ["--permission-mode", "acceptEdits"]
        if scratch:
            args += ["--add-dir", str(scratch)]
    if model:
        args += ["--model", model]
    return args


def prepare_home(home, deny=()):
    """Nothing to write: denied commands are part of the run settings."""
    return []


def version_command():
    return [CLI, "--version"]


def _bound(text):
    text = text if isinstance(text, str) else json.dumps(text)
    if len(text) <= OUTPUT_LIMIT:
        return text
    half = OUTPUT_LIMIT // 2
    return f"{text[:half]}\n[... {len(text) - OUTPUT_LIMIT} characters left out ...]\n{text[-half:]}"


def _results(events):
    """{tool_use_id: (text, is_error)} from the tool results the host sent back to the model."""
    found = {}
    for event in events:
        if event.get("type") != "user":
            continue
        for item in (event.get("message") or {}).get("content") or []:
            if isinstance(item, dict) and item.get("type") == "tool_result":
                content = item.get("content")
                if isinstance(content, list):
                    content = "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
                found[item.get("tool_use_id")] = (str(content or ""), bool(item.get("is_error")))
    return found


def actions(events, stderr=""):
    """The host-neutral action log of a run. Claude Code reports every tool call and its result, so every entry
    is observed. Calls the host refused (permission denials) are logged as blocked."""
    results, log = _results(events), []
    denied = {}
    for event in events:
        if event.get("type") == "result":
            for denial in event.get("permission_denials") or []:
                if isinstance(denial, dict):
                    denied[denial.get("tool_use_id")] = denial
    for event in events:
        if event.get("type") != "assistant":
            continue
        for item in event.get("message", {}).get("content", []) or []:
            if not (isinstance(item, dict) and item.get("type") == "tool_use"):
                continue
            name, data, use_id = item.get("name", ""), item.get("input") or {}, item.get("id")
            text, failed = results.get(use_id, ("", False))
            if use_id in denied:
                log.append({"kind": "blocked", "source": "observed", "tool": name,
                            "command": data.get("command") or data.get("file_path") or "", "reason": text[:300]})
            elif name == "Bash":
                log.append({"kind": "command", "source": "observed", "command": data.get("command", ""),
                            "exit": 1 if failed else 0, "output": _bound(text)})
            elif name in READ_TOOLS:
                log.append({"kind": "read", "source": "observed", "path": data.get(READ_TOOLS[name]), "ok": not failed})
            elif name in SEARCH_TOOLS:
                log.append({"kind": "search", "source": "observed", "pattern": data.get("pattern"),
                            "path": data.get("path")})
            elif name in WRITE_TOOLS:
                log.append({"kind": "write", "source": "observed", "path": data.get(WRITE_TOOLS[name]),
                            "ok": not failed})
            elif name == "Skill":
                log.append({"kind": "skill_load", "source": "observed", "name": str(data.get("skill", "")).split(":")[-1]})
            else:
                log.append({"kind": "tool", "source": "observed", "name": name})
    return log


def exposed_skills(events, home, world):
    """Skills and plugins the host listed in its init event."""
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            plugins = [f"plugin:{p.get('name')}" for p in event.get("plugins") or [] if isinstance(p, dict)]
            return sorted(set(event.get("skills") or []) | set(plugins))
    return []
