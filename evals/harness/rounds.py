"""Rounds (doc 11, Rounds, results and labels): the plan of a round and its manifest.

One rule: a round decides nothing a stored, hashed record cannot show. `round plan` reads a plan file, checks it
against one schema of what it may hold, and writes the round's manifest to the round store: the hash of every
world and case, skill, upstream source, kit part and adapter, and each host's version, as the host's own jail
finds it. Every later gate of the round reads its inputs through this manifest.

Plan file fields (`PLAN`), each with the one shape it may take; anything else is refused with the reason:

- `round`: the round's name, a plain name. Its manifest is `<store>/<round>/manifest.json`.
- `skills`: `{skill: [case ids]}`, at least one skill and one case each. Every case is named: none is added by
  default.
- `hosts`: `[{"adapter": name, "model": text}]`, at least one, each adapter once. `model` is optional; a host that
  does not report the model it used must have one named here.
- `runs`: runs per case, per arm and per host, 1 to 20.

A round's manifest is written once. Planning a round again gives the same manifest or is refused, so a round's
inputs never change under its name. A changed input is a new round.

Run from the repository root:

    python3 evals/harness/rounds.py plan PLAN.json --store DIR

Standard library only.
"""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # its imports leave no bytecode in the kit's folder, which must hold only tracked files
import cases  # noqa: E402
import contain  # noqa: E402
import host  # noqa: E402
import kit  # noqa: E402
import manifest  # noqa: E402
import probes  # noqa: E402
import skills  # noqa: E402
from cases import REPO, CaseError, is_name  # noqa: E402

ADAPTERS = REPO / "adapters"
MANIFEST = "manifest.json"
RUNS = range(1, 21)


class RoundError(RuntimeError):
    """A plan or a round that cannot go on, with the reason. The round stops."""


def _host(value):
    return (isinstance(value, dict) and set(value) <= {"adapter", "model"} and is_name(value.get("adapter"))
            and ("model" not in value or cases.is_text(value["model"])))


PLAN = {
    "round": is_name,
    "skills": lambda v: (isinstance(v, dict) and v and all(
        is_name(k) and isinstance(ids, list) and ids and all(is_name(i) for i in ids) and len(set(ids)) == len(ids)
        for k, ids in v.items())),
    "hosts": lambda v: (isinstance(v, list) and v and all(_host(h) for h in v)
                        and len({h["adapter"] for h in v}) == len(v)),
    "runs": lambda v: type(v) is int and v in RUNS,
}


def read_plan(path):
    """The plan file at `path`, checked against `PLAN`."""
    try:
        data = json.loads(Path(path).read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RoundError(f"{path}: not a UTF-8 JSON plan: {error}") from None
    if not isinstance(data, dict):
        raise RoundError(f"{path}: a plan is one JSON object")
    unknown = sorted(set(data) - set(PLAN))
    missing = sorted(set(PLAN) - set(data))
    if unknown or missing:
        raise RoundError(f"{path}: a plan holds exactly the fields {sorted(PLAN)}; "
                         f"unknown {unknown}, missing {missing}")
    wrong = [field for field, shape in PLAN.items() if not shape(data[field])]
    if wrong:
        raise RoundError(f"{path}: the fields {wrong} do not have their shapes (see rounds.py, PLAN)")
    return data


def adapter(name, root=ADAPTERS):
    """The adapter module `root/<name>/adapter.py`, checked against the host contract."""
    path = Path(root) / name / "adapter.py"
    if not is_name(name) or not path.is_file():
        raise RoundError(f"{name}: no adapter at {path}")
    spec = importlib.util.spec_from_file_location(f"adapter_{name.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        host.check_adapter(module)
    except host.HostError as error:
        raise RoundError(f"{name}: {error}") from None
    if module.NAME != name:
        raise RoundError(f"{path}: the adapter names itself {module.NAME!r}, not {name!r}")
    return module


def tracked_digest(folder):
    """The manifest digest of the files git tracks under `folder`, each a regular file in real folders."""
    folder = Path(folder)
    return manifest.digest({rel: "file " + cases.sha256_bytes(skills.tracked_file(folder, rel))
                            for rel in skills.tracked(folder)})


def host_version(module, **containment):
    """{"path", "sha256", "version"} of the host's program as its own jail finds it, in an empty trigger world."""
    with tempfile.TemporaryDirectory(prefix="hw-round-version-") as scratch:
        (Path(scratch) / "world").mkdir()
        contained = contain.Containment(module, "trigger", Path(scratch) / "world", {}, root=Path(scratch) / "run",
                                        **containment)
        found = probes.versions(contained, [module.CLI]).get(module.CLI)
    if not found:
        raise RoundError(f"{module.NAME}: its program {module.CLI} is not found in its jail")
    return found


def commit(repo=REPO):
    """The commit the working tree is at."""
    done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
                          env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.devnull,
                               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    if done.returncode != 0:
        raise RoundError(f"{repo}: no git commit: {done.stderr.strip()}")
    return done.stdout.strip()


def plan(path, repo=REPO, adapters=ADAPTERS, version=host_version, **containment):
    """The manifest of the round the plan at `path` describes. `version` finds a host's version (`host_version`);
    `containment` passes on to it."""
    data = read_plan(path)
    try:
        found = {"skills": {}, "cases": {}}
        for name, ids in data["skills"].items():
            files, meta = skills.skill_files(Path(repo) / "skills" / name, name)
            source = (meta.get("metadata") or {}).get("source")
            found["skills"][name] = {"sha256": manifest.digest({rel: "file " + cases.sha256_bytes(body)
                                                                for rel, body in files.items()}),
                                     "source": source}
            known = {case.id: case for case in cases.load_cases(name, Path(repo) / "evals" / "skills" / name
                                                                / "cases")}
            absent = [i for i in ids if i not in known]
            if absent:
                raise RoundError(f"{path}: {name} has no cases {absent}")
            found["cases"][name] = {i: known[i].sha256 for i in ids}
        modules = {h["adapter"]: adapter(h["adapter"], adapters) for h in data["hosts"]}
        return {
            "round": data["round"],
            "plan": data,
            "plan_sha256": cases.sha256_file(Path(path)),
            "commit": commit(repo),
            "kit": kit.digest(repo),
            **found,
            "adapters": {name: tracked_digest(Path(adapters) / name) for name in modules},
            "hosts": {h["adapter"]: {"version": version(modules[h["adapter"]], **containment),
                                     "model": h.get("model")} for h in data["hosts"]},
        }
    except (CaseError, kit.KitError, contain.ContainmentError) as error:
        raise RoundError(f"{path}: {error}") from None


def write(record, store, repo=REPO):
    """Write a round's manifest to `store`, read it back and return its path. A round's manifest is written once:
    the same manifest again is kept, and a different one is refused."""
    try:
        folder = kit.store_folder(store, repo) / record["round"]
    except kit.KitError as error:
        raise RoundError(str(error)) from None
    target = folder / MANIFEST
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if os.path.lexists(target):
        if manifest.kind(manifest.entry(target)) != "file" or target.read_text() != text:
            raise RoundError(f"{target}: round {record['round']} already has another manifest; a changed input is "
                             f"a new round")
        return target
    folder.mkdir(parents=True, exist_ok=True)
    fresh = folder / f".{MANIFEST}.{os.getpid()}"
    fresh.write_text(text)
    os.replace(fresh, target)  # replaces a link at the manifest's name, and never writes through it
    if cases.sha256_file(target) != cases.sha256_bytes(text.encode()):
        raise RoundError(f"{target}: the manifest read back is not the one written")
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(prog="rounds.py", description="Plan an eval round.")
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan", help="write the round's manifest to the store")
    planning.add_argument("plan", help="the plan file")
    planning.add_argument("--store", required=True, help="the round store, outside the working tree")
    args = parser.parse_args(argv)
    try:
        print(write(plan(args.plan), args.store))
    except RoundError as error:
        print(f"round: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
