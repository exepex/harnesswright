"""The runs of a round (doc 11, Rounds, results and labels): one run of one case, in one arm, on one host, keyed
by the hashes of its inputs, stored once, and remade only when it is missing or void.

One rule: a run is named by its key, the hash of everything that decides it: the case, every skill an arm
installs, the adapter, the host's version and model from the round's manifest, the arm, the run's number, and the
runner code that affects a run (`RUNNER`). A run whose key holds a bundle is kept, so a resumed round remakes only
missing or voided runs, and a changed input gives a new key, never a changed run.

- `key(record, skill, case_id, arm, host, number)`: the run's key, from the manifest `record`.
- `run(record, store, case, arm, host, number, adapter, drift, version, ...)`: the run with that key in
  `<store>/<round>/runs/<key>/`. A run that holds `bundle/` is kept. Otherwise both arms are built and proved, the
  arm is run in its jail through `host.run`, and its evidence (`evidence.collect`) is stored. A run is void, with
  `void.json` holding why, only for a harness fault: the host failed, or its version is not the manifest's. What
  the agent did is never a void. A jail that fails its audit or a canary in the output raises: the round stops.

Standard library only.
"""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import contain
import evidence
import host
import kit
import manifest
import world
from cases import REPO

ARMS = ("without_skill", "with_skill")
HARNESS = Path(__file__).resolve().parent
# The runner code that affects a run: its jail and gate, the host contract, the world builder and the evidence.
RUNNER = ("audit.py", "cases.py", "contain.py", "evidence.py", "gate.py", "host.py", "manifest.py", "powers.py",
          "scrub.py", "skills.py", "world.py")
BUNDLE, VOID = "bundle", "void.json"


class RunError(RuntimeError):
    """A run that cannot be named or stored, with the reason. The round stops."""


def runner(folder=HARNESS):
    """The hash of the runner code that affects a run."""
    return manifest.digest({name: manifest.entry(Path(folder) / name) for name in RUNNER})


def key(record, skill, case_id, arm, host_name, number, code=None):
    """The key of one run, from the round's manifest `record`. `code` is the runner's hash (`runner`)."""
    if arm not in ARMS or skill not in record["cases"] or case_id not in record["cases"][skill]:
        raise RunError(f"{skill}/{case_id}, {arm}: not a run of round {record['round']}")
    if host_name not in record["hosts"] or not 1 <= number <= record["plan"]["runs"]:
        raise RunError(f"{host_name}, run {number}: not a run of round {record['round']}")
    inputs = {"case": record["cases"][skill][case_id], "skills": record["skills"], "arm": arm, "number": number,
              "adapter": record["adapters"][host_name], "host": record["hosts"][host_name],
              "runner": code or runner()}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()


def folder(record, store, run_key, repo=REPO):
    """The folder of one run in the store, which the store check keeps outside the working tree."""
    runs = Path(store) / record["round"] / "runs"
    try:
        (kit.store_folder(store, repo) / record["round"] / "runs").mkdir(parents=True, exist_ok=True)
        return kit.store_folder(runs, repo) / run_key
    except kit.KitError as error:
        raise RunError(str(error)) from None


def stored(path):
    """("kept", the bundle's folder) for a run whose bundle loads, ("void", why) for a voided one, or None."""
    path = Path(path)
    if (path / BUNDLE).is_dir() and not (path / BUNDLE).is_symlink():
        evidence.load(path / BUNDLE)  # every blob read back by its hash, or it raises
        return "kept", path / BUNDLE
    if (path / VOID).is_file() and not (path / VOID).is_symlink():
        return "void", json.loads((path / VOID).read_text())["reason"]
    return None


def run(record, store, case, arm, host_name, number, adapter, drift, version, skills_root=None, timeout=900,
        repo=REPO, code=None, **containment):
    """The run of `case` in `arm` on `host_name`, number `number`, in round `record`. `version` is the host's
    version as its jail finds it now; `drift` its tools and drift record (`probes.drift`); `containment` passes on
    to `contain.Containment`. Return {"key", "status": "kept", "made" or "void", "bundle" or "reason"}."""
    run_key = key(record, case.skill, case.id, arm, host_name, number, code)
    path = folder(record, store, run_key, repo)
    found = stored(path)
    if found and found[0] == "kept":
        return {"key": run_key, "status": "kept", "bundle": str(found[1])}
    planned = record["hosts"][host_name]
    if version != planned["version"]:
        return _void(path, run_key, f"the host's version {version} is not the manifest's {planned['version']}")
    skills_root = Path(skills_root) if skills_root else Path(repo) / "skills"
    skill_dir = skills_root / case.skill
    with tempfile.TemporaryDirectory(prefix="r-") as scratch:
        scratch = Path(scratch)
        base = world.build(case, adapter, scratch / "a", skills_root)
        other = world.build(case, adapter, scratch / "b", skills_root, True, skill_dir)
        world.prove(case, adapter, base, other, skills_root, skill_dir)  # the arms differ only by the skill
        chosen = other if arm == "with_skill" else base
        contained = contain.Containment(adapter, case.kind, chosen.path, manifest.manifest(chosen.path),
                                        root=scratch / "run", **containment)
        result = host.run(contained, case.prompt, skills=[i.name for i in chosen.installs],
                          model=planned["model"], timeout=timeout)
        layer = evidence.overlay(case, adapter, skills_root, skill_dir)
        # Collected first, failed or not, so a canary in any output stops the round (`scrub.Leak`).
        bundle, blobs = evidence.collect(contained, result, case, arm, layer, drift, version["version"],
                                         planned["model"])
        if bundle["failure"]:  # the host failed, not the agent: a harness fault, so the run is void and remade
            return _void(path, run_key, f"the host failed: {bundle['failure']}")  # scrubbed by `collect`
        path.mkdir(exist_ok=True)
        made = path / f".{BUNDLE}.{os.getpid()}"
        shutil.rmtree(made, ignore_errors=True)
        evidence.store(bundle, blobs, made)  # written and read back beside its name, then moved into place
        if (path / VOID).exists():
            (path / VOID).unlink()  # the void is replaced by the run that remade it
        os.rename(made, path / BUNDLE)
    return {"key": run_key, "status": "made", "bundle": str(stored(path)[1])}


def _void(path, run_key, reason):
    path.mkdir(exist_ok=True)
    fresh = path / f".{VOID}.{os.getpid()}"
    fresh.write_text(json.dumps({"reason": reason}, indent=1) + "\n")
    os.replace(fresh, path / VOID)
    return {"key": run_key, "status": "void", "reason": reason}
