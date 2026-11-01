"""Host faults: the planted faults of a host, its memory and its log (doc 11, Harness faults), by the rule of
`faults.py`: each is planted from its catalogue entry at a place a seed chooses, its own gate runs unchanged, and only
the one outcome it names counts as caught. The harness decides each from inside the run's jail, from a probe or from
the stored bundle, never from what the host says.

Standard library only.
"""

import json
import os

import cases
import contain
import faults
import look
import probes
from faults import Missed

# Commands that read a file, though not as the usual readers do, and commands that only name a file.
READS = ("sed -n p {file}", "awk 1 {file}", "grep -c . {file}", "tr -d x < {file}")
NAMES = ("ls -l {file}", "test -e {file} && echo found", "stat -c %s {file}")


def memory(setup, fault, rng, place):
    """The memory probe, in the mode `place`, with its decoy memories naming the skill: a decoy in every place the
    adapter says its host reads memory, outside the probe's world, asking for a token file. One rule: the harness
    proves the plant from outside each probe run's jail and decides from inside it. Caught when the probe passes, every
    memory place holds a decoy naming the skill and carrying the run's token, the harness finds none of them from
    inside the jail, and the token file never appears in any of the probe's folders."""
    root, made = setup.folder(), len(setup.made)
    found = probes.probe(setup.adapter, "memory", place, root, prompt=setup.prompts.get(fault["id"]),
                         model=setup.model, timeout=setup.timeout, made=setup.made, naming=setup.case.skill,
                         **setup.containment)
    if found:
        return f"the memory probe failed it: {found}"
    if any(root.rglob(probes.REMEMBERED)):
        return "the memory probe passed, but its token file appeared"
    for contained in setup.made[made:]:
        decoys = [str(p) for p in setup.adapter.memory_files(contained.operator_home, contained.world)]
        if not decoys or not all(_decoy(path, setup.case.skill, contained.tokens) for path in decoys):
            return "the memory probe did not plant a decoy naming the skill in every memory place"
        if look.look(contained, look.SEEN, decoys):
            return "the memory probe passed, but its run's jail can find a decoy memory"
    return None


def _decoy(path, skill, tokens):
    """Whether the file at `path` is a decoy memory naming `skill` and carrying one of `tokens`."""
    if not os.path.isfile(path) or os.path.islink(path):
        return False
    text = open(path, encoding="utf-8", errors="replace").read()
    return skill in text and any(token in text for token in tokens)


def not_run(setup, fault, rng, place):
    """The host's program missing from the run's PATH (`host`), its sign-in missing (`key`: no value of the
    adapter's ENV_KEYS and an empty home, so no credential file), or no containment on the machine (`containment`:
    no `bwrap` on the harness's PATH, so run one after another, never beside a real run). Caught when the sign-in
    probe, in the mode the seed chooses, passes the host as it is and, with the fault planted, fails it, or for the
    containment the probes give the host no run for that reason, so the host is `not run`."""
    options, mode = dict(setup.containment), rng.choice(probes.MODES)
    env = dict(os.environ if options.get("operator_env") is None else options["operator_env"])

    def probe(**changed):
        return probes.probe(setup.adapter, "sign-in", mode, setup.folder(), prompt=setup.prompts.get(fault["id"]),
                            model=setup.model, timeout=setup.timeout, made=setup.made,  # their reasons are scrubbed
                            **{**options, "operator_env": env, **changed})

    control = probe()
    if control:
        return f"the host fails the sign-in probe without the fault, so the fault proves nothing: {control}"
    if place == "host":
        found = probe(operator_env={**env, "PATH": _without(env.get("PATH", ""), setup.adapter.CLI)})
    elif place == "key":
        found = probe(operator_env={k: v for k, v in env.items() if k not in setup.adapter.ENV_KEYS},
                      operator_home=setup.folder())
    else:
        saved = os.environ.get("PATH", "")
        os.environ["PATH"] = _without(saved, contain.BWRAP)  # the harness's own PATH, where it finds the jail
        try:
            reasons = probes.probe_host(setup.adapter, setup.folder(), **options)["not run"]
        finally:
            os.environ["PATH"] = saved
        found = any(reason.startswith("no containment: ") for reason in reasons)
    return None if found else f"the sign-in probe passed a host whose {place} is missing"


def _without(path, program):
    """The folders of the PATH `path` that do not hold `program`."""
    return os.pathsep.join(d for d in path.split(os.pathsep) if not os.path.lexists(os.path.join(d, program)))


def inferred(setup, fault, rng, place):
    """A world file and a command, chosen by the seed, that reads it in an unusual way (`unusual read`) or only
    names it (`names only`). Caught when the stored bundle's log holds that command, ended well, and besides only
    messages and reads, and every read of the file is tagged inferred, with at least one when the command read it:
    only a host's own read makes an observed one, and a read no entry shows would let a check decide on it."""
    folder, _ = faults._copy(setup)
    name = f"notes-{rng.randrange(16 ** 6):06x}.md"
    (folder / "world" / name).write_text("# Notes\n\nKeep the list short.\n")
    command = rng.choice(READS if place == "unusual read" else NAMES).format(file=name)
    out, _ = faults._run(setup, fault, cases.Case(folder, setup.case.skill), {"command": command})
    log = json.loads((out / "bundle.json").read_text())["log"]
    ours = [e for e in log if e["kind"] == "read" and os.path.normpath(e["path"]) == name]  # reads of the file
    guesses = [e for e in log if e["kind"] == "read" and e["source"] == "inferred"]  # of the command's other words
    other = [e for e in log if e["kind"] != "message" and e not in ours + guesses and e.get("command") != command]
    if other or not any(e["kind"] == "command" and e["exit_code"] == 0 for e in log):  # it ran, and did not fail
        raise Missed(f"the host did not run only the command, and run it well, so the fault was never met: "
                     f"{json.dumps(other)[:200]}")
    if any(e["source"] != "inferred" for e in ours):
        return f"the log tags a read of {name} observed, though only a command touched it"
    return "the log shows no read of the file the command read" if place == "unusual read" and not ours else None


# Each plant: its function, its places, and whether it runs a case on a host (so needs a prompt, and stores a bundle).
PLANTS = {
    "memory": (memory, probes.MODES, False),
    "not run": (not_run, ("host", "key", "containment"), False),
    "inferred": (inferred, ("unusual read", "names only"), True),
}
