"""The fake host's adapter: the harness contract (`host.CONTRACT`) for the fake host in this folder.

It turns the fake host's sandbox and bundled skills off and keeps only the tools of the power table, and turns
its events into the host-neutral action log. A file the host's shell command names for reading is logged as an
inferred read, since the host reported only the command.
"""

import json
import shlex
from pathlib import Path

import host

NAME = "fakehost"
CLI = "fakehost"
MODEL_HOSTS = ("model.example.test",)
ENV_KEYS = ()
CREDENTIAL_FILES = ()
RUN_ENV = {}
TOOLS = {"read_file": "read", "write_file": "write", "shell": "command", "load_skill": "skill", "spawn": "agent"}
READERS = ("cat", "head", "tail", "sed", "awk", "grep", "tr")  # commands whose file arguments it infers as reads


def skill_dir(world, name):
    return Path(world) / ".fake" / "skills" / name


def memory_files(home, world):
    return [Path(home) / ".fake" / "MEMORY.md", Path(world).parent / "AGENTS.md"]


def environment(env):
    return env


def jail_command(mode, world, model):
    return [CLI, "--world", str(world), "--sandbox", "off", "--no-bundled", "--tools", ",".join(TOOLS)]


def events(stdout):
    found = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            found.append(event)
    return found


def action_log(stdout, home):
    log = []
    for event in events(stdout):
        kind, tool = event.get("event"), event.get("tool")
        if kind == "message":
            log.append(host.entry("message", text=event["text"]))
        elif kind == "refused":
            log.append(host.entry("blocked", action=f"{tool}: {event['detail']}", reason=event["reason"]))
        elif kind == "error" and tool == "write_file":  # the harness decides whether the jail refused it
            log.append({"kind": "failed", "source": "observed", "action": f"{tool}: {event['detail']}",
                        "path": event["detail"], "reason": event["message"]})
        elif kind == "tool" and tool == "read_file":
            log.append(host.entry("read", path=event["path"]))
        elif kind == "tool" and tool == "write_file":
            log.append(host.entry("write", path=event["path"], sha256=host.sha256(event["content"])))
        elif kind == "tool" and tool == "shell":
            log.append(host.entry("command", command=event["command"], exit_code=event["exit"],
                                  output=event["output"]))
            log += [host.entry("read", "inferred", path=path) for path in inferred_reads(event["command"])]
        elif kind == "tool" and tool == "load_skill":
            log.append(host.entry("skill", name=event["name"]))
        elif kind == "tool" and tool == "spawn":
            log.append(host.entry("agent", task=event["task"]))
    return log


def inferred_reads(command):
    try:
        words = shlex.split(command)
    except ValueError:
        return []
    return [word for word in words[1:] if not word.startswith("-")] if words and words[0] in READERS else []


def exposure(stdout, home):
    for event in events(stdout):
        if event.get("event") == "start":
            return {"skills": list(event["skills"]), "tools": list(event["tools"])}
    return None


def run_failure(stdout, returncode, timed_out):
    if timed_out:
        return "timed out"
    if returncode != 0:
        return f"exit code {returncode}"
    if not any(event.get("event") == "done" for event in events(stdout)):
        return "no done event"
    return None
