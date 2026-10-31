"""Eval adapter for the OpenAI Codex command line in non-interactive mode (`codex exec`).

Codex discovers skills in `.agents/skills/` and reads a skill by opening its SKILL.md with a
shell command, so a skill counts as triggered when a command in the JSON event stream opens that
file, or a tool call's arguments name it.
"""

import hashlib
import json
import re
import shlex
from pathlib import Path

NAME = "codex"
CLI = "codex"
# What a sealed run passes on to sign in: these variables, and copies of these files from the real home.
ENV_KEYS = ("CODEX_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL")
CREDENTIAL_FILES = (".codex/auth.json",)
# The model hosts the eval gate allows: the API, and ChatGPT for a ChatGPT sign-in.
MODEL_HOSTS = ("api.openai.com", "chatgpt.com")
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
    """`codex exec` reads its API key from CODEX_API_KEY, not OPENAI_API_KEY; copy the key over if needed."""
    env = dict(env)
    if not env.get("CODEX_API_KEY") and env.get("OPENAI_API_KEY"):
        env["CODEX_API_KEY"] = env["OPENAI_API_KEY"]
    return env


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

    Codex also emits `error` events while it retries a connection ("Reconnecting... 2/5"). They fail
    the run only when the turn never completed. A timed-out task run always fails: partial work is not
    a finished task. A timed-out trigger run counts when items already arrived, because the trigger
    decision comes first.
    """
    completed = any(e.get("type") == "turn.completed" for e in events)
    for wanted in ("turn.failed",) if completed else ("turn.failed", "error"):
        for event in reversed(events):
            if event.get("type") == wanted:
                detail = event.get("error") or event.get("message") or ""
                if isinstance(detail, dict):
                    detail = detail.get("message", "")
                return f"host reported {wanted}: {detail}".rstrip(": ")
    if timed_out:
        if mode == "trigger" and any(True for _ in _items(events)):
            return None
        return "timed out"
    if returncode not in (0, None):
        return f"exit code {returncode}"
    if not completed:
        return "no turn.completed event"
    return None


# The eval harness contract (evals/harness/host.py). The jail enforces the power table, so Codex's own sandbox and
# approvals are off, and its bundled skills are off. Every thread, sub-agents included, writes a session file in
# the run's home, which holds each finished item with its full detail, so the action log is read from there: the
# `--json` stream on stdout leaves out what sub-agents do.
RUN_ENV = {}
# `functions.exec` runs JavaScript that calls the nested tools listed in its description, so each nested tool is a
# tool too, named `functions.exec/NAME`. Image viewing, goals and web search are turned off. The jail has no MCP
# server, so the MCP resource tools have nothing to read.
TOOLS = {"functions.exec": "command", "functions.exec/exec_command": "command",
         "functions.exec/write_stdin": "command", "functions.exec/apply_patch": "write",
         "functions.exec/clock__curr_time": "wait",
         "functions.exec/list_mcp_resources": "wait", "functions.exec/list_mcp_resource_templates": "wait",
         "functions.exec/read_mcp_resource": "wait",
         "collaboration.spawn_agent": "agent", "collaboration.followup_task": "agent",
         "collaboration.send_message": "agent", "collaboration.interrupt_agent": "agent",
         "collaboration.list_agents": "agent", "collaboration.wait_agent": "wait", "functions.wait": "wait",
         "clock.sleep": "wait", "functions.request_user_input": "wait",
         "functions.request_user_input_async": "wait"}  # `exec` mode answers no question
SKILL_ROW = re.compile(r"^- ([A-Za-z0-9._-]+): .*\(file: \S+\)$")
NESTED = re.compile(r"^### `([^`]+)`", re.M)


def jail_command(mode, world, model):
    command = [CLI, "exec", "--json", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox",
               "-c", "skills.bundled.enabled=false", "--disable", "view_image", "--disable", "goals",
               "-c", 'web_search="disabled"', "--cd", str(world)]
    return command + (["--model", model] if model else []) + ["-"]


def _threads(home):
    """The records of each thread's session file, one list per thread."""
    for path in sorted(Path(home).glob(".codex/sessions/**/rollout-*.jsonl")):
        records = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and isinstance(record.get("payload"), dict):
                records.append(record)
        yield records


def _session_lines(home):
    for records in _threads(home):
        yield from records


def _finished_items(home):
    found = [(record["payload"].get("started_at_ms") or 0, record["payload"]["item"])
             for record in _session_lines(home)
             if record.get("type") == "event_msg" and record["payload"].get("type") == "item_completed"
             and isinstance(record["payload"].get("item"), dict)]
    return [item for _, item in sorted(found, key=lambda pair: pair[0])]


def _command_text(command):
    if isinstance(command, list):
        if len(command) == 3 and command[0].rsplit("/", 1)[-1] in SHELLS and command[1].startswith("-"):
            return command[2]
        return shlex.join(str(word) for word in command)
    return str(command)


def action_log(stdout, home):
    log = []
    for item in _finished_items(home):
        kind = item.get("type")
        if kind == "CommandExecution":
            exit_code = item.get("exit_code")
            log.append({"kind": "command", "source": "observed", "command": _command_text(item.get("command")),
                        "exit_code": exit_code if isinstance(exit_code, int) else None,
                        "output": str(item.get("aggregated_output") or "")[:4000]})
            for parsed in item.get("parsed_cmd") or []:  # Codex's own reading of the command, so inferred
                if isinstance(parsed, dict) and parsed.get("type") == "read" and isinstance(parsed.get("path"), str):
                    log.append({"kind": "read", "source": "inferred", "path": parsed["path"]})
                    found = re.search(r"skills/([^/]+)/SKILL\.md$", parsed["path"])
                    if found:
                        log.append({"kind": "skill", "source": "inferred", "name": found.group(1)})
        elif kind == "FileChange":
            for path, change in (item.get("changes") or {}).items():
                if item.get("status") != "completed":
                    log.append({"kind": "failed", "source": "observed", "action": f"write: {path}", "path": str(path),
                                "reason": str(item.get("stderr") or item.get("stdout") or "").strip()})
                    continue
                content = change.get("content") if isinstance(change, dict) else None
                digest = hashlib.sha256(content.encode()).hexdigest() if isinstance(content, str) else None
                log.append({"kind": "write", "source": "observed", "path": str(path),
                            "sha256": digest if change.get("type") != "delete" else None})
        elif kind == "SubAgentActivity" and item.get("kind") == "started":
            log.append({"kind": "agent", "source": "observed", "task": str(item.get("agent_path") or "")})
        elif kind == "AgentMessage":
            text = "".join(part.get("text", "") for part in item.get("content") or [] if isinstance(part, dict))
            log.append({"kind": "message", "source": "observed", "text": text})
    return log


def exposure(stdout, home):
    """Every skill and tool any thread was given, from the session files. A thread's `world_state` records hold its
    state, each later one only the keys that changed; its `additional_tools` record describes the tools nested in
    `functions.exec`. None when there is no thread, or when a thread does not report both lists, or the nested
    tools of an `exec` it has, as no report is never 'nothing'."""
    skills, tools, threads = set(), set(), 0
    for records in _threads(home):
        state, nested = {}, None
        for record in records:
            payload = record["payload"]
            if payload.get("type") == "additional_tools":
                nested = (nested or set()) | _nested_tools(payload.get("tools"))
            if record.get("type") == "world_state" and isinstance(payload.get("state"), dict):
                state.update(payload["state"])
        if not records:
            continue
        listed, given = state.get("host_skills"), state.get("top_level_tools")
        body = listed.get("body") if isinstance(listed, dict) else None
        if not isinstance(body, str) or not isinstance(given, dict) or ("functions.exec" in given and nested is None):
            return None
        threads += 1
        skills |= _skill_rows(body)
        tools |= set(given) | {f"functions.exec/{name}" for name in nested or ()}
    if not threads:
        return None
    # A namespace such as `functions` is listed beside its tools (`functions.exec`); only the tools are tools.
    leaves = [tool for tool in tools if not any(other.startswith(tool + ".") for other in tools)]
    return {"skills": sorted(skills), "tools": sorted(leaves)}


def _skill_rows(body):
    """The skills of the "Available skills" section. Every row there counts: one that does not parse is kept whole,
    so it is never a declared skill and stops the round."""
    section, rows = False, []
    for line in body.splitlines():
        if line.startswith("#"):
            section = line.strip() == "### Available skills"
        elif section and line.startswith("- "):
            rows.append(line)
    return {found.group(1) if found else row for row, found in zip(rows, map(SKILL_ROW.match, rows))}


def _nested_tools(declared):
    """The tools nested in `functions.exec`, from the headings of its description."""
    names = set()
    for space in declared if isinstance(declared, list) else []:
        for tool in space.get("tools") or [] if isinstance(space, dict) and space.get("name") == "functions" else []:
            if isinstance(tool, dict) and tool.get("name") == "exec":
                names |= set(NESTED.findall(str(tool.get("description", ""))))
    return names


def run_failure(stdout, returncode, timed_out):
    return failure(parse_events(stdout), returncode, timed_out, "task")
