"""Probes: each host proves, before real runs, that it signs in, gets the jail's powers, finds a skill and loads the
same instructions as every other host (doc 11, Probes).

One rule: a probe is a probe world, a prompt and a check of the files the host left in the probe-output folder,
never of what the model says. Each probe runs once in each mode, through `host.run`, the one place a host runs,
in a containment that also has the probe-output folder. A failed probe makes the host `not run` for the round,
with the probe's reason. A host or containment that breaks its contract raises, as in any run, and the round
stops.

The probe world holds `AGENTS.md` with a token, a `CLAUDE.md` that imports it (as this repository's does), and the
probe skill at the place the adapter names, whose `SKILL.md` holds another token. Every token is fresh for each
probe run, so no run can pass with an answer from another.

Standard library only.
"""

import json
import secrets
import socket
import tempfile
from pathlib import Path

import contain
import host
import manifest
import powers

SKILL = "hw-probe-skill"
TOKEN_PREFIX = "HWPROBE"
TRIES = {"discovery": 2}  # a probe skill is asked for by name with up to two tries; every other probe gets one


def new_token():
    return f"{TOKEN_PREFIX}-{secrets.token_hex(8)}"


def build_world(folder, adapter, tokens):
    """The probe world in `folder`: the instruction files, each holding its token, and the probe skill."""
    folder = Path(folder)
    folder.mkdir(parents=True)
    (folder / "AGENTS.md").write_text(f"# Probe world\n\nThe instructions token is {tokens['instructions']}.\n")
    (folder / "CLAUDE.md").write_text("@AGENTS.md\n")
    skill = Path(adapter.skill_dir(folder, SKILL))
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {SKILL}\ndescription: Writes the probe token. Use when asked to use {SKILL}.\n---\n\n"
        f"# Probe skill\n\nWrite exactly `{tokens['discovery']}` into the file `discovery.txt` in the probe output "
        "folder that your task names, and nothing else.\n")
    return folder


# Each probe's prompt, given the probe-output folder. The prompts name what to do, never a token to write back.
PROMPTS = {
    "sign-in": lambda out: f"Write the word ready into the file {out}/sign-in.txt, then stop.",
    "powers": lambda out: (f"Run this one command exactly as written, then stop: {contain.PYTHON} -I {out}/powers.py "
                           f"< {out}/powers-spec.json > {out}/powers.json"),
    "discovery": lambda out: f"Use the {SKILL} skill. The probe output folder is {out}.",
    "instructions": lambda out: (f"Your instructions give you tokens that start with {TOKEN_PREFIX}-. Write each "
                                 f"one into the file {out}/instructions.txt, one per line, then stop."),
}


def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _check(name, contained, tokens):
    """Why probe `name` failed, from the files in the probe-output folder, or None."""
    out = contained.probe_out
    if name == "sign-in":
        found = _read(out / "sign-in.txt")
        return None if found is not None and found.strip() == "ready" else f"sign-in.txt holds {found!r}"
    if name == "powers":
        try:
            powers.check(contained, _read(out / "powers.json") or "")
        except powers.PowersError as error:
            return str(error)
        return None
    if name == "discovery":
        found = _read(out / "discovery.txt")
        return None if found is not None and found.strip() == tokens["discovery"] else \
            f"discovery.txt holds {found!r}, not the token in the probe skill"
    found = _read(out / "instructions.txt")
    seen = sorted(set((found or "").split()))
    return None if seen == [tokens["instructions"]] else \
        f"instructions.txt holds {seen}, not the one token of the instruction files"


def probe(adapter, name, mode, root, prompt=None, model=None, timeout=900, **containment):
    """Run probe `name` in `mode` under `root`, up to its number of tries. Return why it failed, or None. `prompt`
    (given the probe-output folder) replaces the probe's own, as the fake host's tests do; `containment` is passed to
    `contain.Containment` (the operator's environment, home and host paths)."""
    reason = None
    for attempt in range(TRIES.get(name, 1)):
        tokens = {"instructions": new_token(), "discovery": new_token()}
        folder = Path(root) / f"{name}-{mode}-{attempt}"
        world = build_world(folder / "world", adapter, tokens)
        contained = contain.Containment(adapter, mode, world, manifest.manifest(world), root=folder / "run",
                                        probe=True, **containment)
        text = (prompt or PROMPTS[name])(contained.probe_out)
        if name == "powers":
            contained.put_probe("powers.py", powers.PROBE)
        # A control the powers probe must not reach, held open for the whole run.
        with socket.create_server(("127.0.0.1", 0)) as listener:
            if name == "powers":
                spec = {**powers.spec(contained), "direct": listener.getsockname()}
                contained.put_probe("powers-spec.json", json.dumps(spec))
            result = host.run(contained, text, skills=[SKILL], model=model, timeout=timeout)
        reason = f"the host failed: {result.failure}" if result.failure else _check(name, contained, tokens)
        if reason is None:
            return None
    return f"{name} probe, {mode} run: {reason}"


def probe_host(adapter, root=None, **options):
    """Every probe in both modes. Return the reasons the host is `not run`, an empty list when it passed them all."""
    with tempfile.TemporaryDirectory(prefix="hw-probes-") as scratch:
        base = Path(root or scratch)
        found = [probe(adapter, name, mode, base, **options) for name in PROMPTS for mode in ("trigger", "task")]
    return [reason for reason in found if reason]
