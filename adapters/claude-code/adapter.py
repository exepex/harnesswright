"""Eval adapter for Claude Code, the reference host, for the eval harness's host contract (evals/harness/host.py).

Runs `claude -p` in the jail with the prompt on stdin and reads its stream-json events.
"""

import hashlib
import json
import re
from pathlib import Path

NAME = "claude-code"
CLI = "claude"
# What a sealed run passes on to sign in: these variables, and copies of these files from the real home.
ENV_KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN")
CREDENTIAL_FILES = (".claude/.credentials.json",)
# The model host the eval gate allows.
MODEL_HOSTS = ("api.anthropic.com",)


def skill_dir(workspace, skill_name):
    """Project-level skills folder that Claude Code discovers."""
    return Path(workspace) / ".claude" / "skills" / skill_name


def memory_files(home, world):
    """Where Claude Code reads memory and the user's own instructions outside the world, for a home and a world:
    the user's CLAUDE.md and rules, the project's auto memory under `~/.claude/projects`, and the CLAUDE.md files
    of a folder above the project, at its top and in its `.claude` folder."""
    claude, above = Path(home) / ".claude", Path(world).parent
    project = re.sub(r"[^A-Za-z0-9]", "-", str(world))
    return [claude / "CLAUDE.md", claude / "rules" / "hw-probe.md", claude / "projects" / project / "memory" /
            "MEMORY.md", above / "CLAUDE.md", above / "CLAUDE.local.md", above / ".claude" / "CLAUDE.md"]


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


def resolved_model(events):
    """The model the host actually used, from its init event."""
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init" and event.get("model"):
            return str(event["model"])
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


def _planted(command, flag, value):
    at = command.index(flag) + 1
    return command[:at] + [value] + command[at + 1:]


# The host faults the harness plants (host.PLANTED): the jail settings without what turns bundled skills off, and
# the tools without Bash, the one command tool.
PLANTS = {"bundled skills": lambda command: _planted(command, "--settings", json.dumps(
              {**{k: v for k, v in JAIL_SETTINGS.items() if k != "skillOverrides"}, "disableBundledSkills": False})),
          "no commands": lambda command: _planted(command, "--tools",
                                                  ",".join(t for t in TOOLS if TOOLS[t] != "command"))}


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
                 "exit_code": int(code.group(1)) if code else (None if failed else 0), "output": text}]
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
    """Why the run failed, or None. A timed-out run always fails: partial work is not a finished task."""
    events = parse_events(stdout)
    for event in events:
        if event.get("type") == "result" and event.get("is_error"):
            return f"host reported an error: {event.get('subtype', 'error')}"
    if timed_out:
        return "timed out"
    if returncode not in (0, None):
        return f"exit code {returncode}"
    if not any(e.get("type") == "result" for e in events):
        return "no result event"
    return None


# The host's usage fields of each neutral count (host.TOKENS): in its result's modelUsage, and in its usage. Its
# input counts neither cache read nor cache write, so the neutral input adds them. A cache write is one count, which
# does not tell a 5-minute write (an API key sign-in) from a 1-hour one (a subscription sign-in).
USAGE = {"input": (("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens"),
                   ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")),
         "cache read": (("cacheReadInputTokens",), ("cache_read_input_tokens",)),
         "cache write": (("cacheCreationInputTokens",), ("cache_creation_input_tokens",)),
         "output": (("outputTokens",), ("output_tokens",))}


def tokens(stdout, home):
    """The host's own token counts by model, or None when it reported none: those of its last result event, which
    holds the run's running totals, for each model in its modelUsage (subagents included), else its usage under the
    model its init event names."""
    events = parse_events(stdout)
    results = [event for event in events if event.get("type") == "result"]
    last = results[-1] if results else {}
    models, usage = last.get("modelUsage"), last.get("usage")
    if isinstance(models, dict) and models and all(isinstance(m, dict) and "inputTokens" in m
                                                   for m in models.values()):
        return {model: {name: sum(counts.get(f, 0) for f in fields[0]) for name, fields in USAGE.items()}
                for model, counts in models.items()}
    if isinstance(usage, dict) and "input_tokens" in usage:
        return {resolved_model(events) or "unknown model": {name: sum(usage.get(f, 0) for f in fields[1])
                                                            for name, fields in USAGE.items()}}
    return None
