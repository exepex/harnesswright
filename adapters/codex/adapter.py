"""Eval adapter for the OpenAI Codex command line in non-interactive mode (`codex exec`), for the eval harness's host
contract (evals/harness/host.py).

Codex discovers skills in `.agents/skills/` and reads a skill by opening its SKILL.md with a shell command, so a
skill load is inferred from a command that read that file (`action_log`).
"""

import hashlib
import importlib.util
import json
import os
import re
import shlex
from pathlib import Path
from urllib.parse import unquote

# Its session files are read in their own module, beside this one, as every loader loads only this file by path.
_SPEC = importlib.util.spec_from_file_location("codex_sessions", Path(__file__).with_name("sessions.py"))
sessions = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sessions)

NAME = "codex"
CLI = "codex"
# What a sealed run passes on to sign in: these variables, and copies of these files from the real home.
ENV_KEYS = ("CODEX_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL")
CREDENTIAL_FILES = (".codex/auth.json",)
# The model hosts the eval gate allows: the API, and ChatGPT for a ChatGPT sign-in.
MODEL_HOSTS = ("api.openai.com", "chatgpt.com")
SHELLS = ("bash", "sh", "zsh", "dash")


def skill_dir(workspace, skill_name):
    """Repository-level skills folder that Codex discovers."""
    return Path(workspace) / ".agents" / "skills" / skill_name


NO_SKILLS = {"includeInstructions"}  # the only keys of a skills record without a body, seen live in 0.166.0


def memory_files(home, world):
    """Where Codex reads memory and the user's own instructions outside the world, for a home and a world: its
    global AGENTS.override.md and AGENTS.md and memories under CODEX_HOME (`~/.codex`), and the same instruction
    files in a folder above the project."""
    codex, above = Path(home) / ".codex", Path(world).parent
    return [codex / "AGENTS.override.md", codex / "AGENTS.md", codex / "memories" / "MEMORY.md",
            codex / "memories" / "memory_summary.md", codex / "memories" / "raw_memories.md",
            above / "AGENTS.override.md", above / "AGENTS.md"]


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
SKILL_ROOT = re.compile(r"^- `r\d+` = `[^`]+`$")
NESTED = re.compile(r"^### `([^`]+)`", re.M)


def jail_command(mode, world, model):
    command = [CLI, "exec", "--json", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox",
               "-c", "skills.bundled.enabled=false", "--disable", "view_image", "--disable", "goals",
               "-c", 'web_search="disabled"', "--cd", str(world)]
    return command + (["--model", model] if model else []) + ["-"]


def _bundled(command):
    """The jail command with Codex's bundled skills on: without its pair that turns them off."""
    at = command.index("skills.bundled.enabled=false")
    return command[:at - 1] + command[at + 1:]


# The host faults the harness plants (host.PLANTED). Codex runs commands through its shell and exec tools.
PLANTS = {"bundled skills": _bundled,
          "no commands": lambda command: command[:-1] + ["--disable", "shell_tool", "--disable", "unified_exec", "-"]}


def _session_lines(home):
    for records in sessions.threads(home):
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
                        "output": str(item.get("aggregated_output") or "")})
            # Codex's own reading of the command, so inferred; only a command that worked read anything. A path is
            # relative to the command's folder, which Codex gives as a file URL.
            cwd = unquote(str(item.get("cwd") or "").removeprefix("file://"))
            for parsed in item.get("parsed_cmd") or [] if exit_code == 0 else []:
                if isinstance(parsed, dict) and parsed.get("type") == "read" and isinstance(parsed.get("path"), str):
                    path = os.path.normpath(os.path.join(cwd, parsed["path"])) if cwd else parsed["path"]
                    log.append({"kind": "read", "source": "inferred", "path": path})
                    found = re.search(r"skills/([^/]+)/SKILL\.md$", path)
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
    """One rule: the exposure is every skill and tool named in any record of any thread, and each thread must have
    given one full report. A thread's first `world_state` record lists its skills and top-level tools, and later ones
    list only what changed, so nothing is ever taken away. Its `additional_tools` records describe the tools nested
    in `functions.exec`. None when a thread gave no full report, a record lists one in another form, or a thread has
    `exec` without its nested tools, as no report is never 'nothing'."""
    skills, tools, threads = set(), set(), 0
    for records in sessions.threads(home):
        named, nested, full = set(), None, False
        for record in records:
            payload = record["payload"]
            if payload.get("type") == "additional_tools":
                found = _nested_tools(payload.get("tools"))
                nested = (nested or set()) | found if found else nested
            state = payload.get("state") if record.get("type") == "world_state" else None
            if not isinstance(state, dict):
                continue
            listed, top = state.get("host_skills", {"body": ""}), state.get("top_level_tools", {})
            body = listed.get("body") if isinstance(listed, dict) else None
            if isinstance(listed, dict) and "body" not in listed and set(listed) <= NO_SKILLS:
                body = ""  # the one shape Codex gives a thread with no skills
            if not isinstance(body, str) or not isinstance(top, dict):
                return None
            full = full or ("host_skills" in state and "top_level_tools" in state)
            skills |= _skill_rows(body)
            named |= set(top)
        if not records:
            continue
        if not full or ("functions.exec" in named and nested is None):
            return None
        threads += 1
        tools |= named | {f"functions.exec/{name}" for name in nested or ()}
    if not threads:
        return None
    # A namespace such as `functions` is listed beside its tools (`functions.exec`); only the tools are tools.
    leaves = [tool for tool in tools if not any(other.startswith(tool + ".") for other in tools)]
    return {"skills": sorted(skills), "tools": sorted(leaves)}


def _skill_rows(body):
    """The skills in a skill list. Every row counts but a skill root's row under "Skill roots": a row that does not
    parse is kept whole, so it is never a declared skill and stops the round, whatever the layout."""
    section, skills = None, set()
    for line in body.splitlines():
        if line.startswith("#"):
            section = line.strip()
        elif line.startswith("- ") and not (section == "### Skill roots" and SKILL_ROOT.match(line)):
            found = SKILL_ROW.match(line)
            skills.add(found.group(1) if found else line)
    return skills


def _nested_tools(declared):
    """The tools nested in `functions.exec`, from the headings of its description. Only a positive report counts:
    None when the record declares no `exec` or one that names no tool, as it always nests at least
    `exec_command`."""
    names = set()
    for space in declared if isinstance(declared, list) else []:
        for tool in space.get("tools") or [] if isinstance(space, dict) and space.get("name") == "functions" else []:
            if isinstance(tool, dict) and tool.get("name") == "exec":
                names |= set(NESTED.findall(str(tool.get("description", ""))))
    return names or None


def run_failure(stdout, returncode, timed_out):
    """Why the run failed, or None.

    Codex also emits `error` events while it retries a connection ("Reconnecting... 2/5"). They fail the run only
    when the turn never completed. A timed-out run always fails: partial work is not a finished task.
    """
    events = parse_events(stdout)
    completed = any(e.get("type") == "turn.completed" for e in events)
    for wanted in ("turn.failed",) if completed else ("turn.failed", "error"):
        for event in reversed(events):
            if event.get("type") == wanted:
                detail = event.get("error") or event.get("message") or ""
                if isinstance(detail, dict):
                    detail = detail.get("message", "")
                return f"host reported {wanted}: {detail}".rstrip(": ")
    if timed_out:
        return "timed out"
    if returncode not in (0, None):
        return f"exit code {returncode}"
    if not completed:
        return "no turn.completed event"
    return None


tokens = sessions.tokens  # (stdout, home): read from every thread's session file, as the log is
