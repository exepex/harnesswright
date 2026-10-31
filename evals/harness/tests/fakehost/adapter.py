"""Adapter for the fake host of the harness tests (fake_host.py). Tests copy the program to a folder outside the
repository and set CLI to it, so the jail mounts that folder and nothing of the repository."""

import json
from pathlib import Path

NAME = "fake"
CLI = "fake-host"
ENV_KEYS = ("FAKE_HOST_KEY", "FAKE_HOST_FAULT", "FAKE_HOST_SKILLS")
CREDENTIAL_FILES = ()
HOST_SKILLS = ()


def skill_dir(world, name):
    return Path(world) / ".fake" / "skills" / name


def environment(env):
    return env


def command(mode, world, scratch=None, model=None, deny=()):
    """Commands may write the world and scratch in a task run, and nothing in a trigger run."""
    args = [CLI]
    for folder in ((world, scratch) if mode == "task" else ()):
        if folder:
            args += ["--write", str(folder)]
    return args


def prepare_home(home, deny=()):
    return []


def version_command():
    return [CLI, "--version"]


def parse_events(stdout):
    events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def actions(events, stderr=""):
    log = []
    for event in events:
        if event.get("type") == "action":
            entry = {k: v for k, v in event.items() if k != "type"}
            entry["source"] = "observed"
            log.append(entry)
    return log


def exposed_skills(events, home, world):
    for event in events:
        if event.get("type") == "init":
            return sorted(event.get("skills") or [])
    return []


def resolved_model(events):
    return "fake-model"


def final_message(events):
    for event in reversed(events):
        if event.get("type") == "result":
            return event.get("text") or ""
    return ""


def failure(events, returncode, timed_out, mode):
    for event in events:
        if event.get("type") == "result" and event.get("error"):
            return f"host reported an error: {event['error']}"
    if timed_out:
        return "timed out"
    if returncode not in (0, None):
        return f"exit code {returncode}"
    return None
