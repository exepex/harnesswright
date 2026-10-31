#!/usr/bin/python3 -I
"""A fake agent host for the harness's own tests. It does what a real host does that the harness must handle,
without a model: it loads instruction files and any memory it finds in its home, finds skills in its discovery
folder, runs commands and writes files, and reports every action as one JSON event per line.

The prompt (standard input) is either one of the probes' prompts, which it understands, or a JSON plan:
{"actions": [{"read": path}, {"write": [path, text]}, {"run": command}, {"env": true}], "final": text}.

FAKE_HOST_KEY must be set, as a real host needs its sign-in. FAKE_HOST_FAULT picks a planted fault:
`no-commands` (the host cannot run commands). `--write FOLDER` (repeatable) names the folders its commands may
write, like a real host's sandbox settings.
"""

import json
import os
import re
import subprocess
import sys

MEMORY_FILES = (".claude/CLAUDE.md", ".claude/memory/MEMORY.md", ".codex/AGENTS.md", ".codex/memories/notes.md",
                ".agents/AGENTS.md", "AGENTS.md", "CLAUDE.md")


def emit(**event):
    print(json.dumps(event), flush=True)


WRITABLE = []


def run(command):
    """Run a command in the fake host's own sandbox, as real hosts do: everything read-only except the folders
    given with --write, and no network."""
    if os.environ.get("FAKE_HOST_FAULT") == "no-commands":
        emit(type="action", kind="blocked", command=command, reason="this host cannot run commands")
        return ""
    sandbox = ["bwrap", "--die-with-parent", "--unshare-net", "--dev-bind", "/", "/", "--ro-bind", "/", "/",
               "--dev", "/dev", "--proc", "/proc"]
    for folder in WRITABLE:
        sandbox += ["--bind", folder, folder]
    done = subprocess.run(sandbox + ["--chdir", os.getcwd(), "/bin/sh", "-c", command], capture_output=True,
                          text=True, timeout=120)
    output = done.stdout + done.stderr
    emit(type="action", kind="command", command=command, exit=done.returncode, output=output)
    return output


def read(path):
    try:
        with open(path) as handle:
            text = handle.read()
        emit(type="action", kind="read", path=path, ok=True)
        return text
    except OSError as error:
        emit(type="action", kind="read", path=path, ok=False, error=str(error))
        return None


def main():
    args = sys.argv[1:]
    if args == ["--version"]:
        print("fake-host 1.0")
        return 0
    while len(args) >= 2 and args[0] == "--write":
        WRITABLE.append(args[1])
        args = args[2:]
    if not os.environ.get("FAKE_HOST_KEY"):
        emit(type="result", error="not signed in")
        return 1
    prompt = sys.stdin.read()
    home = os.environ.get("HOME", "")
    # Memory: a host that keeps memory in its home follows what it says.
    for relative in MEMORY_FILES:
        path = os.path.join(home, relative)
        if os.path.isfile(path):
            for command in re.findall(r"running(?: the shell command)?: (.+)", open(path).read()):
                run(command.strip())
    instructions = ""
    if os.path.isfile("AGENTS.md"):
        instructions = open("AGENTS.md").read()  # loaded, as hosts load instruction files: not a read action
    skills_dir = os.path.join(".fake", "skills")
    skills = sorted(os.listdir(skills_dir)) if os.path.isdir(skills_dir) else []
    emit(type="init", skills=skills + json.loads(os.environ.get("FAKE_HOST_SKILLS", "[]")))
    final = "done"
    try:
        plan = json.loads(prompt)
    except json.JSONDecodeError:
        plan = None
    if isinstance(plan, dict):
        for action in plan.get("actions", []):
            if "read" in action:
                read(action["read"])
            elif "write" in action:
                path, text = action["write"]
                try:
                    with open(path, "w") as handle:
                        handle.write(text)
                    emit(type="action", kind="write", path=path, ok=True)
                except OSError as error:
                    emit(type="action", kind="write", path=path, ok=False, error=str(error))
            elif "run" in action:
                run(action["run"])
            elif action.get("env"):
                final = json.dumps(dict(os.environ))
        final = plan.get("final", final)
    elif "power_probe.py" in prompt:
        final = run("python3 power_probe.py")
    elif "code word" in prompt:
        match = re.search(r"code word is (\S+?)\.", instructions)
        if match:
            run(f"echo {match.group(1)}")
    else:
        asked = re.search(r"Use the (\S+) skill", prompt)
        if asked and asked.group(1) in skills:
            emit(type="action", kind="skill_load", name=asked.group(1))
            text = open(os.path.join(skills_dir, asked.group(1), "SKILL.md")).read()
            for command in re.findall(r"^    (.+)$", text, re.M):
                run(command)
        elif "ready" in prompt:
            final = "ready"
    emit(type="result", text=final)
    return 0


if __name__ == "__main__":
    sys.exit(main())
