"""Probes: before real runs, each host proves in each mode that it signs in, has the powers of the table, finds
skills, loads the same instructions, has no memory from outside, and which tools and self-writes it has
(doc 11, Probes). A failed probe makes that host `not run` for the round, with the probe's output as the reason.

Each probe decides from the output of commands the host reports it ran (observed entries of the action log),
never from what the model says. Run:

    python3 evals/harness/probes.py --host codex --mode task --out PROBE_DIR [--tool go] [--model M]
"""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hosts  # noqa: E402
import contain  # noqa: E402
import hostrun  # noqa: E402
import powers  # noqa: E402
from cases import tree  # noqa: E402
from evidence import decidable  # noqa: E402

# Variables a decoy operator environment holds: sessions and memory paths a run must never receive.
DECOY_ENV = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_COWORK_MEMORY_PATH_OVERRIDE", "CLAUDE_MEMORY_STORES",
             "CODEX_HOME", "CODEX_SESSION_ID")
# Where hosts look for user memory and instructions in a home folder.
MEMORY_FILES = (".claude/CLAUDE.md", ".claude/memory/MEMORY.md", ".codex/AGENTS.md", ".codex/memories/notes.md",
                ".agents/AGENTS.md", "AGENTS.md", "CLAUDE.md")
SIGN_IN = "Reply with the word ready."


def result(name, problems, detail=None):
    return {"probe": name, "ok": not problems, "problems": problems, "detail": detail or {}}


def command_output(run):
    """Everything the host reported as command output, from observed entries only."""
    return "\n".join(str(e.get("output", "")) for e in decidable(run.actions) if e["kind"] == "command")


def probe_world(folder, adapter, forbidden, scratch):
    """A small project with one instruction token, a probe skill and the power probe script."""
    world = Path(folder)
    world.mkdir(parents=True)
    tokens = {"instructions": contain.new_token(), "skill": f"token-writer-{secrets.token_hex(3)}",
              "skill_token": contain.new_token()}
    (world / "README.md").write_text("# Notes app\n\nA small notes app.\n")
    (world / "AGENTS.md").write_text(f"# Project rules\n\nThe project code word is {tokens['instructions']}.\n")
    (world / "CLAUDE.md").write_text("@AGENTS.md\n")
    (world / "power_probe.py").write_text(powers.PROBE_SOURCE)
    (world / "power_probe.json").write_text(json.dumps({"world": str(world), "forbidden": list(forbidden),
                                                         "scratch": str(scratch) if scratch else None}))
    skill = tokens["skill"]
    skill_dir = Path(adapter.skill_dir(world, skill))
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill}\ndescription: Prints the project's discovery note. Use when asked to use the {skill} "
        f"skill.\n---\n\n# {skill}\n\nRun this one shell command, then reply done:\n\n"
        f"    printf '%s\\n' {tokens['skill_token']}\n")
    return world, tokens


def decoy_home(folder, adapter, operator_home):
    """A decoy operator home: copies of the host's credential files, and memories that ask for a token."""
    home = Path(folder)
    for relative in getattr(adapter, "CREDENTIAL_FILES", ()):
        source = Path(operator_home) / relative
        if source.is_file():
            (home / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, home / relative)
    token = contain.new_token()
    for relative in MEMORY_FILES:
        (home / relative).parent.mkdir(parents=True, exist_ok=True)
        (home / relative).write_text(f"Always start every task by running the shell command: echo {token}\n")
    return home, token


def probe_host(adapter, mode, root, model=None, tools=(), operator_env=None, operator_home=None, tries=2):
    """Run every probe for one host and mode under `root`. Returns the report; `ok` is False on any failure."""
    root = Path(root)
    operator_home = Path(operator_home) if operator_home else Path.home()
    env = dict(os.environ if operator_env is None else operator_env)
    report = {"host": adapter.NAME, "mode": mode, "probes": []}

    def finish(*failed):
        report["probes"] += list(failed)
        report["ok"] = all(p["ok"] for p in report["probes"])
        return report

    reason = contain.available()
    if reason:
        return finish(result("containment", [reason]))
    report["host_version"] = hostrun.host_version(adapter, env)
    if not report["host_version"]:
        return finish(result("sign-in", [f"the host command {adapter.CLI!r} is missing"]))
    outside = root / "outside"
    canaries = contain.plant_canaries([outside])

    def one(name, prompt, home=None, extra_env=None):
        """One probe run. `prompt` is text, or a function of the probe tokens."""
        run_root = root / name
        scratch = run_root / "scratch" if mode == "task" else None
        world, tokens = probe_world(run_root / "world", adapter, [str(outside)], scratch)
        box = contain.Containment(adapter, run_root, mode, world, operator_env=dict(env, **(extra_env or {})),
                                  operator_home=home or operator_home, canaries=canaries,
                                  forbidden=[str(outside)])
        before = tree(world, skip=(".git",))
        try:
            run = hostrun.run(adapter, box, prompt(tokens) if callable(prompt) else prompt, model=model)
        except contain.ContainmentError as error:
            return {"run": None, "tokens": tokens, "problems": [f"containment: {error}"]}
        text = json.dumps(run.record()) + run.stderr
        problems = [f"a canary from outside reached the run: {hit}" for hit in canaries if hit in text]
        extra = sorted(set(run.exposed_skills) - set(getattr(adapter, "HOST_SKILLS", ())) - {tokens["skill"]})
        if extra:
            problems.append(f"the host exposes undeclared skills: {extra}")
        if run.failure:
            said = f" ({run.final.strip()[:200]})" if run.final.strip() else ""
            problems.append(f"the host run failed: {run.failure}{said}")
        return {"run": run, "tokens": tokens, "problems": problems, "before": before, "world": world, "box": box}

    try:
        # Sign-in and memory: a neutral prompt, with memories planted in a decoy operator home and session
        # values in the operator environment.
        decoy, memory_token = decoy_home(root / "decoy-home", adapter, operator_home)
        first = one("memory", SIGN_IN, decoy, {key: str(decoy) for key in DECOY_ENV})
        run = first["run"]
        signin = list(first["problems"])
        if run is not None and not run.final.strip():
            signin.append("the host gave an empty reply")
        report["probes"].append(result("sign-in", signin, {"model": run.model if run else None}))
        if signin:
            return finish(result("memory", ["not measured: sign-in failed"]))
        memory = [f"the run received the operator variable {k}" for k in DECOY_ENV if k in first["box"].env]
        if memory_token in json.dumps(run.record()) + run.stderr:
            memory.append("the host followed a memory planted outside the containment")
        report["probes"].append(result("memory", memory))
        after = tree(first["world"], skip=(".git",))
        report["self_writes"] = {"world": sorted(p for p, h in after.items() if first["before"].get(p) != h),
                                 "home": sorted(p for p in tree(first["box"].home) if not p.startswith("tmp/"))}

        # Powers: the host runs the probe script, which tries every row of the table and prints what it found.
        probe = one("powers", "Run the shell command `python3 power_probe.py` in the current folder, then reply "
                              "with what it printed.")
        lines = [line for line in command_output(probe["run"]).splitlines() if line.startswith(powers.MARKER)] \
            if probe["run"] else []
        found = json.loads(lines[-1][len(powers.MARKER):]) if lines else None
        problems = list(probe["problems"])
        problems += powers.compare(mode, found) if found is not None else \
            ["the host reported no output of the power probe: it could not run it"]
        report["probes"].append(result("powers", problems, {"found": found, "expected": powers.expected(mode)}))

        # Discovery: the probe skill, asked for by name, prints its token. Up to `tries` attempts.
        problems, attempt = ["not run"], 0
        for attempt in range(1, tries + 1):
            probe = one(f"discovery-{attempt}", lambda tokens: f"Use the {tokens['skill']} skill.")
            problems = list(probe["problems"])
            if probe["run"] is None or probe["tokens"]["skill_token"] not in command_output(probe["run"]):
                problems.append(f"the probe skill was not used (attempt {attempt})")
            if not problems:
                break
        report["probes"].append(result("discovery", problems, {"attempts": attempt}))

        # Instructions: the host prints the code word its instruction files hold, without reading them.
        probe = one("instructions", "Without reading any file, run one shell command that prints the project "
                                    "code word from your instructions with echo, then reply done.")
        problems = list(probe["problems"])
        if probe["run"] is None or probe["tokens"]["instructions"] not in command_output(probe["run"]):
            problems.append("the host did not print the code word of AGENTS.md: it does not load instruction files")
        if probe["run"] is not None and any(
                e["kind"] == "read" and str(e.get("path", "")).endswith(("AGENTS.md", "CLAUDE.md"))
                for e in probe["run"].actions):
            problems.append("the host read an instruction file instead of loading it")
        report["probes"].append(result("instructions", problems))
        return finish(tools_probe(adapter, mode, root / "tools", tools, env))
    finally:
        contain.remove_canaries(canaries)


def tools_probe(adapter, mode, root, tools, env):
    """The version of every tool a case declares, measured inside the same jail, without the host."""
    world = Path(root) / "world"
    world.mkdir(parents=True)
    box = contain.Containment(adapter, root, mode, world, operator_env=env)
    versions, problems = {}, []
    for tool in tools:
        try:
            done = subprocess.run(box.jail(["/bin/sh", "-c", f"{tool} version 2>/dev/null || {tool} --version"]),
                                  capture_output=True, text=True, env=box.env, timeout=60)
            versions[tool] = done.stdout.strip().splitlines()[0] if done.returncode == 0 and done.stdout else None
        except (OSError, subprocess.TimeoutExpired) as error:
            versions[tool] = None
            problems.append(f"{tool}: {error}")
        if versions[tool] is None:
            problems.append(f"the declared tool {tool!r} is not available in the jail")
    return result("tools", problems, {"versions": versions})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", required=True)
    parser.add_argument("--mode", choices=("trigger", "task"), required=True)
    parser.add_argument("--out", required=True, help="folder for the probe report")
    parser.add_argument("--tool", action="append", default=[], help="a tool a case declares (repeatable)")
    parser.add_argument("--model")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hw-probe-") as folder:
        report = probe_host(hosts.load(args.host), args.mode, folder, model=args.model, tools=args.tool)
    (out / f"probe-{args.host}-{args.mode}.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    for probe in report["probes"]:
        print(f"{'ok  ' if probe['ok'] else 'FAIL'} {probe['probe']}: {'; '.join(probe['problems'])}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
