"""The runs of a round (doc 11, Rounds, results and labels): one run of one case, in one arm, on one host, keyed
by the hashes of its inputs, stored once, and remade only when it is missing or void.

One rule: a run is named by its key, the hash of everything that decides it: the case, every skill an arm
installs, the adapter, the host's version and model from the round's manifest, the arm, the run's number, the run's
own settings (`drift`, which decides what evidence counts as the agent's, and the time budget), and the runner code
that affects a run (`RUNNER`). The jail's settings are not in the key: the jail is audited on every run, and one
that fails its audit stops the round. A run whose key holds a bundle is kept, so a resumed round remakes only
missing or voided runs, and a changed input gives a new key, never a changed run.

- `arms(record, case)`: the arms a case runs in: without and with the skill, and for a task case of a skill the
  plan gives a previous version, `previous_version`, which installs the skill as the manifest's commit holds it.
  A skill the manifest records as `absent`, with cases but no folder yet, runs without the skill only, and a case
  of a situation a plain agent cannot fail (`skill_only`) with it only.
- `key(record, skill, case_id, arm, host, number, drift, timeout)`: the run's key, from the manifest `record`.
- `run(record, store, case, arm, host, number, adapter, drift, version, ...)`: the run with that key in
  `<store>/<round>/runs/<key>/`. A run that holds `bundle/` is kept. Otherwise both arms are built and proved, the
  arm is run in its jail through `host.run`, and its evidence (`evidence.collect`) is stored. A run is void, with
  `void.json` holding why, only for a harness fault: the host failed, its version is not the manifest's, or a
  without-skill run's evidence holds a long passage of the skill's own text (`backstop.check`), whose bundle is then
  kept under `voids/<n>/` for a judge and never scored; shorter matches go to `backstop.json` beside the bundle. What the
  agent did, a run that timed out included, is never a void. A voided slot gets one remake; voided again, it stays
  empty. `void.json` keeps every void of the slot, a remade one too, for the void rate. A jail that fails its audit
  or a canary in the output raises: the round stops. A run is made only from the repository at the round's commit,
  so it builds exactly the inputs the manifest hashed.
- `pinned(record, case, arm)`: the one test of whether a run pins its skill's load (doc 12, Proven use). A pinned run
  whose evidence proves no load (`evidence.loaded`) is `not loaded`, never a void: its bundle is kept under
  `not-loaded/<n>/` and `not-loaded.json` holds why, with its own try count. It is tried once more at once; not
  loaded again, the slot stays unscored and is not run again.

Standard library only.
"""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import contextlib

import backstop
import contain
import evidence
import host
import kit
import manifest
import rounds
import skills
import world
from cases import ARMS, PREVIOUS, REPO, SKILL_ONLY

HARNESS = Path(__file__).resolve().parent
# The runner code that affects a run: its jail and gate, the host contract, the world builder and the evidence.
RUNNER = ("audit.py", "backstop.py", "cases.py", "contain.py", "evidence.py", "gate.py", "host.py", "lint.py",
          "manifest.py", "powers.py", "runs.py", "scrub.py", "skills.py", "textruns.py", "world.py")
BUNDLE, VOID, VOIDS, SHORT = "bundle", "void.json", "voids", "backstop.json"
UNLOADED, UNLOADED_RUNS = "not-loaded.json", "not-loaded"
TIMEOUT = 900  # seconds a run may take, unless the caller names another
TRIES = 2  # a voided slot gets at most one remake (doc 11, Blocked actions and voids)
LOAD_TRIES = 2  # a pinned run that is not loaded is tried once more (doc 12, Proven use)


class RunError(RuntimeError):
    """A run that cannot be named or stored, with the reason. The round stops."""


def runner(folder=HARNESS):
    """The hash of the runner code that affects a run."""
    return manifest.digest({name: manifest.entry(Path(folder) / name) for name in RUNNER})


def skill_only(record, skill, case_id):
    """True for a case of a situation a plain agent cannot fail (`cases.SKILL_ONLY`), which runs with the skill only."""
    return record.get("situations", {}).get(skill, {}).get("cases", {}).get(case_id) in SKILL_ONLY


def pinned(record, case, arm):
    """True for a task run of the with-skill or the previous version's arm in a round whose manifest pins the load
    (its `pinned` flag): only such a run can be `not loaded`."""
    return case.kind == "task" and arm in ("with_skill", PREVIOUS) and record.get("pinned") is True


def arms(record, case):
    """The arms `case` runs in, in round `record`: `ARMS`, and `PREVIOUS` for a task case of a skill the plan gives
    a previous version. Trigger cases measure the description that triggers the skill under test only."""
    if case.skill in record.get("absent", []):  # no folder yet: a baseline round runs without the skill only
        return ARMS[:1]
    if skill_only(record, case.skill, case.id):
        return ARMS[1:]
    later = (PREVIOUS,) if case.kind == "task" and case.skill in record.get("previous", {}) else ()
    return ARMS + later


def key(record, skill, case_id, arm, host_name, number, drift, timeout=TIMEOUT, code=None):
    """The key of one run, from the round's manifest `record` and the run's own settings: `drift`, the host's tools
    and drift record, and `timeout`, its time budget in seconds (a run that timed out is scored). `code` is the
    runner's hash (`runner`)."""
    known = ARMS[:1] if skill in record.get("absent", []) else ARMS + ((PREVIOUS,) if skill in record.get(
        "previous", {}) else ())
    if skill_only(record, skill, case_id):
        known = ARMS[1:]
    if arm not in known or skill not in record["cases"] or case_id not in record["cases"][skill]:
        raise RunError(f"{skill}/{case_id}, {arm}: not a run of round {record['round']}")
    if host_name not in record["hosts"] or not 1 <= number <= record["plan"]["runs"]:
        raise RunError(f"{host_name}, run {number}: not a run of round {record['round']}")
    inputs = {"skill": skill, "case_id": case_id, "case": record["cases"][skill][case_id], "skills": record["skills"],
              "arm": arm, "number": number, "drift": drift, "timeout": timeout,
              "adapter": record["adapters"][host_name], "host": record["hosts"][host_name],
              "runner": code or runner()}
    if arm == PREVIOUS:
        inputs["previous"] = record["previous"][skill]
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()


def folder(record, store, run_key, repo=REPO):
    """The folder of one run in the store, which the store check keeps outside the working tree."""
    runs = Path(store) / record["round"] / "runs"
    try:
        (kit.store_folder(store, repo) / record["round"] / "runs").mkdir(parents=True, exist_ok=True)
        return kit.store_folder(runs / run_key, repo)  # the slot itself, resolved, so a link at it is checked too
    except kit.KitError as error:
        raise RunError(str(error)) from None


def stored(path):
    """("kept", the bundle's folder) for a run whose bundle loads, ("void", [why, for each void]) for a voided one,
    or None."""
    path = Path(path)
    if (path / BUNDLE).is_dir() and not (path / BUNDLE).is_symlink():
        evidence.load(path / BUNDLE)  # every blob read back by its hash, or it raises
        return "kept", path / BUNDLE
    if (path / VOID).is_file() and not (path / VOID).is_symlink():
        return "void", json.loads((path / VOID).read_text())["reasons"]
    return None


def run(record, store, case, arm, host_name, number, adapter, drift, version, timeout=TIMEOUT, repo=REPO,
        **containment):
    """The run of `case` in `arm` on `host_name`, number `number`, in round `record`, from the repository `repo`
    at the round's commit. `version` is the host's version as its jail finds it now; `drift` its tools and drift
    record (`probes.drift`); `containment` passes on to `contain.Containment`. Return {"key", "status", and
    "bundle" or "reason"}: `kept` or `made` with its bundle, `void` with why, `empty` for a slot voided twice,
    which gets no more remakes, or `not loaded` for a pinned slot with no proven load in either try."""
    if rounds.commit(repo) != record["commit"]:  # the inputs the run builds are the ones the manifest hashed
        raise RunError(f"{repo} is not at round {record['round']}'s commit {record['commit']}")
    run_key = key(record, case.skill, case.id, arm, host_name, number, drift, timeout)
    path = folder(record, store, run_key, repo)
    found = stored(path)
    if found and found[0] == "kept":
        return {"key": run_key, "status": "kept", "bundle": str(found[1])}
    voids = found[1] if found else []
    if len(voids) >= TRIES:
        return {"key": run_key, "status": "empty", "reason": "; ".join(voids)}
    unloaded = _reasons(path / UNLOADED)
    if len(unloaded) >= LOAD_TRIES:
        return {"key": run_key, "status": "not loaded", "reason": "; ".join(unloaded)}
    planned = record["hosts"][host_name]
    if version != planned["version"]:
        return _void(path, run_key, voids, f"the host's version {version} is not the manifest's "
                                           f"{planned['version']}")
    if arm not in arms(record, case):
        raise RunError(f"{case.skill}/{case.id}: the round does not run it in {arm}")
    skills_root = skills.folders(repo)
    with contextlib.ExitStack() as stack:
        skill_dir = skills_root.get(case.skill)
        if arm == PREVIOUS:  # the previous version, read and hashed again through the one reader of it
            kept = record["previous"][case.skill]
            try:
                skill_dir, _ = stack.enter_context(rounds.previous(repo, case.skill, kept["commit"], kept["sha256"]))
            except rounds.RoundError as error:
                raise RunError(str(error)) from None
        scratch = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="r-")))
        absent = case.skill in record.get("absent", [])  # no folder yet: only the without-skill arm is built
        base = world.build(case, adapter, scratch / "a", skills_root)
        other = None if absent else world.build(case, adapter, scratch / "b", skills_root, True, skill_dir)
        world.prove(case, adapter, base, other, skills_root, skill_dir)  # the arms differ only by the skill
        chosen = base if arm == "without_skill" else other
        # The skill's own runs, read from the proved arm before the host can change it (`backstop.protected`).
        own = backstop.protected(case, base, skill_dir, repo) if arm == "without_skill" else None
        contained = contain.Containment(adapter, case.kind, chosen.path, manifest.manifest(chosen.path),
                                        root=scratch / "run", **containment)
        result = host.run(contained, case.prompt, skills=[i.name for i in chosen.installs],
                          model=planned["model"], timeout=timeout)
        layer = evidence.overlay(case, adapter, skills_root, skill_dir)
        # Collected first, failed or not, so a canary in any output stops the round (`scrub.Leak`).
        bundle, blobs = evidence.collect(contained, result, case, arm, layer, drift, version["version"],
                                         planned["model"])
        if bundle["failure"] and not result.timed_out:  # the host failed, not the agent: a harness fault
            return _void(path, run_key, voids, f"the host failed: {bundle['failure']}")  # scrubbed by `collect`
        # A run that timed out is what the agent did in the time it had, and is scored like any other.
        # After `collect`, so a canary has stopped the round already.
        found = None if own is None else backstop.check(bundle, blobs.__getitem__, own)
        path.mkdir(exist_ok=True)
        if found and found["void"]:  # the run saw the skill: void, with its evidence kept where no reader scores it
            kept = path / VOIDS / str(len(voids))
            shutil.rmtree(kept, ignore_errors=True)
            kept.parent.mkdir(exist_ok=True)
            evidence.store(bundle, blobs, kept / BUNDLE)
            where, length, span = found["void"][0]
            return _void(path, run_key, voids, f"fingerprint hit: {length} words of the skill's own text in {where}: "
                                               f"{span[:200]}")
        text = (Path(skill_dir) / "SKILL.md").read_text(errors="replace") if skill_dir else ""
        missed = pinned(record, case, arm) and not evidence.loaded(bundle, case.skill, layer["paths"], text)
        if missed:  # kept where no reader scores it, under its own marker: not a void, never a harness fault
            kept = path / UNLOADED_RUNS / str(len(unloaded))
            shutil.rmtree(kept, ignore_errors=True)
            kept.parent.mkdir(exist_ok=True)
            evidence.store(bundle, blobs, kept / BUNDLE)
            _mark(path / UNLOADED, [*unloaded, "the run's evidence proves no load of the skill"])
        else:
            made = path / f".{BUNDLE}.{os.getpid()}"
            shutil.rmtree(made, ignore_errors=True)
            evidence.store(bundle, blobs, made)  # written and read back beside its name, then moved into place
            if found is not None:
                (path / SHORT).write_text(json.dumps({"short": found["short"]}, indent=1) + "\n")
            os.rename(made, path / BUNDLE)
    if missed:  # tried once more; not loaded then too, the slot is `not loaded` and stays so
        return run(record, store, case, arm, host_name, number, adapter, drift, version, timeout, repo, **containment)
    return {"key": run_key, "status": "made", "bundle": str(stored(path)[1])}


def misses(path):
    """How many tries of the run slot at `path` (`folder`) were not loaded: the one count of them, which the run
    gate's stop and the pinned-load rate both read."""
    return len(_reasons(Path(path) / UNLOADED))


def _reasons(marker):
    """The reasons a slot's marker file keeps, one for each try it names, or none."""
    return json.loads(marker.read_text())["reasons"] if marker.is_file() and not marker.is_symlink() else []


def _mark(marker, reasons):
    fresh = marker.with_name(f".{marker.name}.{os.getpid()}")
    fresh.write_text(json.dumps({"reasons": reasons}, indent=1) + "\n")
    os.replace(fresh, marker)


def _void(path, run_key, voids, reason):
    path.mkdir(exist_ok=True)
    _mark(path / VOID, [*voids, reason])
    return {"key": run_key, "status": "void", "reason": reason}
