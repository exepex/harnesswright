"""Probes: each host proves, before real runs, that it signs in, gets the jail's powers, finds a skill and loads the
same instructions as every other host (doc 11, Probes).

One rule: a probe is a probe world, a prompt and a check that the file the host left in the probe-output folder is
right and that the host's own report, its exposure and action log, shows it did the act, never of what the model
says. Each probe runs once in each mode, through `host.run`, the one place a host runs, in a containment that also
has the probe-output folder. A failed probe makes the host `not run` for the round, with the probe's reason. A host
or containment that breaks its contract raises, as in any run, and the round stops.

The probe world holds `AGENTS.md` with a token, a `CLAUDE.md` that imports it (as this repository's does), and the
probe skill at the place the adapter names, whose `SKILL.md` holds another token. Every token is fresh for each
probe run, so no run can pass with an answer from another.

Standard library only.
"""

import json
import os
import re
import secrets
import shlex
import socket
import stat
import tempfile
from pathlib import Path

import contain
import host
import manifest
import powers

SKILL = "hw-probe-skill"
TOKEN_PREFIX = "HWPROBE"
TOKEN = re.compile(rf"{TOKEN_PREFIX}-[0-9a-f]{{16}}")
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


def powers_command(out):
    """The one command the powers probe asks the host to run."""
    return " ".join([contain.PYTHON, "-I", shlex.quote(f"{out}/powers.py"), "<",
                     shlex.quote(f"{out}/powers-spec.json"), ">", shlex.quote(f"{out}/powers.json")])


# Each probe's prompt, given the probe-output folder. The prompts name what to do, never a token to write back.
PROMPTS = {
    "sign-in": lambda out: f"Write the word ready into the file {out}/sign-in.txt, then stop.",
    "powers": lambda out: f"Run this one command exactly as written, then stop: {powers_command(out)}",
    "discovery": lambda out: f"Use the {SKILL} skill. The probe output folder is {out}.",
    "instructions": lambda out: (f"Your instructions give you tokens that start with {TOKEN_PREFIX}-. Write each "
                                 f"one into the file {out}/instructions.txt, one per line, then stop. Do not read "
                                 "any file."),
}


def _read(path, limit=65536):
    """A file the host left, read only when it is a regular file: a link the host made is never followed out of
    the jail, so it reads as missing."""
    try:
        handle = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    with os.fdopen(handle, "rb") as opened:
        if not stat.S_ISREG(os.fstat(opened.fileno()).st_mode):
            return None
        return opened.read(limit).decode("utf-8", errors="replace")


# The actions a probe of a host action lets the host take, as entries of its log: any other entry fails the probe.
ALLOWED = {
    # Only the one command it was given, so the output is the probe's own and nothing else wrote it.
    "powers": lambda e, out, tokens: e["kind"] == "message" or (
        e["kind"] == "command" and e["command"].strip() == powers_command(out)),
    # Only writing what it already knows: no read, no skill, and no command that does not carry the token it writes.
    "instructions": lambda e, out, tokens: e["kind"] in ("message", "write") or (
        e["kind"] == "command" and tokens["instructions"] in e["command"]),
}


def _check(name, contained, tokens, result):
    """Why probe `name` failed, or None. One rule: the file the probe asks for is right, and the host's own report
    (its exposure and action log) shows it did what the probe tests, not a way around it."""
    out, log = contained.probe_out, result.log
    other = [e for e in log if name in ALLOWED and not ALLOWED[name](e, out, tokens)]
    if other:
        return f"the host did more than the probe asks: {json.dumps(other[0])[:200]}"
    if name == "sign-in":
        found = _read(out / "sign-in.txt")
        return None if found is not None and found.strip() == "ready" else \
            f"sign-in.txt holds {found and found[:80]!r}"
    if name == "powers":  # the host ran the probe as given, and its output is this run's
        if not any(e["kind"] == "command" for e in log):
            return "the host's log shows no command that ran the powers probe"
        try:
            powers.check(contained, _read(out / "powers.json") or "", nonce=tokens["powers"])
        except powers.PowersError as error:
            return str(error)
        return None
    if name == "discovery":  # the host found the skill where the adapter says, and loaded it
        if SKILL not in (result.exposure or {}).get("skills", []):
            return f"the host did not expose {SKILL}, which is where its adapter says skills are"
        if not any(e["kind"] == "skill" and e["name"] == SKILL for e in log):
            return f"the host's log shows no load of {SKILL}"
        found = _read(out / "discovery.txt")
        return None if found is not None and found.strip() == tokens["discovery"] else \
            f"discovery.txt holds {found and found[:80]!r}, not the token in the probe skill"
    seen = sorted(set(TOKEN.findall(_read(out / "instructions.txt") or "")))
    return None if seen == [tokens["instructions"]] else \
        f"instructions.txt holds {seen[:5]}, not the one token of the instruction files"


def probe(adapter, name, mode, root, prompt=None, model=None, timeout=900, **containment):
    """Run probe `name` in `mode` under `root`, up to its number of tries. Return why it failed, or None. `prompt`
    (given the probe-output folder) replaces the probe's own, as the fake host's tests do; `containment` is passed to
    `contain.Containment` (the operator's environment, home and host paths)."""
    reason = None
    for attempt in range(TRIES.get(name, 1)):
        tokens = {"instructions": new_token(), "discovery": new_token(), "powers": new_token()}
        Path(root).mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix=f"{name}-{mode}-{attempt}-", dir=root))
        world = build_world(folder / "world", adapter, tokens)
        contained = contain.Containment(adapter, mode, world, manifest.manifest(world), root=folder / "run",
                                        probe=True, **containment)
        text = (prompt or PROMPTS[name])(contained.probe_out)
        if name == "powers":
            contained.put_probe("powers.py", powers.PROBE)
        # A control the powers probe must not reach, held open for the whole run.
        with socket.create_server(("127.0.0.1", 0)) as listener:
            if name == "powers":
                spec = {**powers.spec(contained), "direct": listener.getsockname(),
                        "nonce": tokens["powers"]}
                contained.put_probe("powers-spec.json", json.dumps(spec))
            result = host.run(contained, text, skills=[SKILL], model=model, timeout=timeout)
        reason = f"the host failed: {result.failure}" if result.failure else _check(name, contained, tokens, result)
        if reason is None:
            return None
    return f"{name} probe, {mode} run: {reason}"


def probe_host(adapter, root=None, **options):
    """Every probe in both modes. Return the reasons the host is `not run`, an empty list when it passed them all."""
    with tempfile.TemporaryDirectory(prefix="hw-probes-") as scratch:
        base = Path(root or scratch)
        found = [probe(adapter, name, mode, base, **options) for name in PROMPTS for mode in ("trigger", "task")]
    return [reason for reason in found if reason]
