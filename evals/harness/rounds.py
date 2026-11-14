"""Rounds (doc 11, Rounds, results and labels): the plan of a round and its manifest.

One rule: a round decides nothing a stored, hashed record cannot show. `round plan` reads a plan file, checks it
against one schema of what it may hold, and writes the round's manifest to the round store: the hash of every
world and case, every skill an arm installs with its upstream source, kit part and adapter, and each host's
version, as the host's own jail finds it. Every later gate of the round reads its inputs through this manifest.

Plan file fields (`PLAN`), each with the one shape it may take; anything else is refused with the reason:

- `round`: the round's name, a plain name. Its manifest is `<store>/<round>/manifest.json`.
- `skills`: `{skill: [case ids]}`, at least one skill and one case each. Every case is named: none is added by
  default.
- `hosts`: `[{"adapter": name, "model": text}]`, at least one, each adapter once. `model` is required: a host
  that does not report the model it used (Codex does not) must have one named here, and a host's default model
  changes over time, so every plan pins the model each host runs.
- `runs`: runs per case, per arm and per host, 1 to 20.
- `previous` (optional): `{skill: commit}`, for a skill of `skills`, the full commit of its previous version. Its
  task cases then run in a third arm, `previous_version`, with the skill as that commit holds it (`previous`).

A round's manifest is written once. Planning a round again gives the same manifest or is refused, so a round's
inputs never change under its name. A changed input is a new round.

Run from the repository root:

    python3 evals/harness/rounds.py plan PLAN.json --store DIR [--host-path PATH ...]
    python3 evals/harness/rounds.py run ROUND --store DIR [--host-path PATH ...] [--seed N]

`--host-path` names a host's install under the operator's home, which its jail refuses unless it is named.
`round run` takes a planned round through its gates (`gates.py`).

Standard library only.
"""

import argparse
import contextlib
import importlib.util
import re
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

sys.modules.setdefault("rounds", sys.modules[__name__])  # run as a script, `gates` imports this copy, not another

ADAPTERS = REPO / "adapters"
MANIFEST = "manifest.json"
RUNS = range(1, 21)
COMMIT = re.compile(r"[0-9a-f]{40}")


class RoundError(RuntimeError):
    """A plan or a round that cannot go on, with the reason. The round stops."""


def _host(value):
    return (isinstance(value, dict) and set(value) == {"adapter", "model"} and is_name(value["adapter"])
            and cases.is_text(value["model"]))


PLAN = {
    "round": is_name,
    "skills": lambda v: (isinstance(v, dict) and v and all(
        is_name(k) and isinstance(ids, list) and ids and all(is_name(i) for i in ids) and len(set(ids)) == len(ids)
        for k, ids in v.items())),
    "hosts": lambda v: (isinstance(v, list) and v and all(_host(h) for h in v)
                        and len({h["adapter"] for h in v}) == len(v)),
    "runs": lambda v: type(v) is int and v in RUNS,
    "previous": lambda v: (isinstance(v, dict) and v and all(
        is_name(k) and isinstance(c, str) and COMMIT.fullmatch(c) for k, c in v.items())),
}
OPTIONAL = {"previous": {}}


def read_plan(path):
    """The plan file at `path`, checked against `PLAN`."""
    try:
        data = json.loads(Path(path).read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RoundError(f"{path}: not a UTF-8 JSON plan: {error}") from None
    if not isinstance(data, dict):
        raise RoundError(f"{path}: a plan is one JSON object")
    unknown = sorted(set(data) - set(PLAN))
    missing = sorted(set(PLAN) - set(data) - set(OPTIONAL))
    if unknown or missing:
        raise RoundError(f"{path}: a plan holds the fields {sorted(PLAN)}, {sorted(OPTIONAL)} optional; "
                         f"unknown {unknown}, missing {missing}")
    wrong = [field for field, shape in PLAN.items() if field in data and not shape(data[field])]
    if wrong:
        raise RoundError(f"{path}: the fields {wrong} do not have their shapes (see rounds.py, PLAN)")
    if not set(data.get("previous", {})) <= set(data["skills"]):
        raise RoundError(f"{path}: previous names a skill the plan does not run")
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
    """The manifest digest of the files git tracks under `folder`, each a regular file in real folders, by the
    entries the world builder copies: contents and the executable bit."""
    folder = Path(folder)
    found = {}
    for rel in skills.tracked(folder):
        skills.tracked_file(folder, rel)  # a regular file in real folders, never a link
        found[rel] = manifest.entry(folder / rel)
    return manifest.digest(found)


def skill(repo, name):
    """{"sha256", "source", "upstream"} of the skill `name`: the hash of its tracked files, the upstream source its
    metadata names, and the hash of the copy of that source stored under `evals/skills/NAME/upstream/`, or None
    when there is none."""
    known = skills.folders(repo)
    if name not in known:
        raise RoundError(f"no skill named {name!r} in the repository")
    _, meta = skills.skill_files(known[name], name)
    upstream = Path(repo) / "evals" / "skills" / name / "upstream"
    return {"sha256": tracked_digest(known[name]),
            "source": (meta.get("metadata") or {}).get("source"),
            "upstream": tracked_digest(upstream) if upstream.is_dir() and not upstream.is_symlink() else None}


@contextlib.contextmanager
def previous(repo, name, at, sha256=None):
    """The folder of the skill `name` as commit `at` holds it, the one `skills.folders` reads there, in a scratch
    worktree of `repo` that is removed afterwards. It is read as the version under test is (`skills.skill_files`),
    so a version a run could not install is refused here. With `sha256`, its tracked files must hash to it, as the
    manifest recorded. The one place a previous version is read: at plan time, by the lint gate and for every run."""
    if not COMMIT.fullmatch(at or ""):
        raise RoundError(f"{at!r}: a previous version is named by its full commit")
    with tempfile.TemporaryDirectory(prefix="hw-previous-") as scratch:
        tree = Path(scratch) / "tree"
        # No hooks: the repository's own post-checkout hook would run outside any jail and could change the tree.
        _git(repo, "-c", f"core.hooksPath={os.devnull}", "worktree", "add", "--detach", "--quiet", str(tree),
             f"{at}^{{commit}}")
        try:
            known = skills.folders(tree)
            if name not in known:
                raise RoundError(f"commit {at} holds no skill named {name!r}")
            try:
                skills.skill_files(known[name], name)
            except CaseError as error:
                raise RoundError(f"{name} at {at}: {error}") from None
            found = tracked_digest(known[name])
            if sha256 is not None and found != sha256:
                raise RoundError(f"{name} at {at} hashes to {found}, not the manifest's {sha256}")
            yield known[name], {"commit": at, "path": known[name].relative_to(tree).as_posix(), "sha256": found}
        finally:  # removed even when the read failed; a removal that fails never hides why the read did
            _git(repo, "worktree", "remove", "--force", str(tree), check=False)


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


def _git(repo, *args, check=True):
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                          env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.devnull,
                               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    if done.returncode != 0 and check:
        raise RoundError(f"{repo}: git {args[0]} failed: {done.stderr.strip()}")
    return done.stdout


def commit(repo=REPO):
    """The commit the working tree is at. The tree must be clean, nothing changed and nothing untracked, so that
    commit holds every input the manifest hashes and the round can be recomputed from the repository alone."""
    changed = _git(repo, "status", "--porcelain", "--untracked-files=all").splitlines()
    if changed:
        raise RoundError(f"{repo}: a round is planned from a clean tree; changed or untracked: "
                         f"{', '.join(line[3:] for line in changed[:10])}")
    return _git(repo, "rev-parse", "HEAD").strip()


def plan(path, repo=REPO, adapters=ADAPTERS, version=host_version, at=commit, **containment):
    """The manifest of the round the plan at `path` describes. `version` finds a host's version (`host_version`)
    and `at` the commit (`commit`); `containment` passes on to `version`."""
    data = read_plan(path)
    try:
        found, installed, known_cases = {"cases": {}}, set(data["skills"]), {}
        for name, ids in data["skills"].items():
            root = Path(repo) / "evals" / "skills" / name / "cases"
            absent = [i for i in ids if not (root / i).is_dir() or (root / i).is_symlink()]
            if absent:
                raise RoundError(f"{path}: {name} has no cases {absent}")
            known = known_cases[name] = {i: cases.Case(root / i, name) for i in ids}  # only the cases it names
            found["cases"][name] = {i: known[i].sha256 for i in ids}
            installed.update(sibling for i in ids for sibling in known[i].siblings or ())
        found["skills"] = {name: skill(repo, name) for name in sorted(installed)}  # every skill an arm installs
        found["previous"] = {}
        for name, earlier in sorted(data.get("previous", {}).items()):
            if not any(case.kind == "task" for case in known_cases[name].values()):
                raise RoundError(f"{path}: previous names {name}, which the plan runs no task case of")
            with previous(repo, name, earlier) as (_, kept):
                if kept["sha256"] == found["skills"][name]["sha256"]:
                    raise RoundError(f"{path}: {name} at {earlier} is the same as the version under test")
                found["previous"][name] = kept
        modules = {h["adapter"]: adapter(h["adapter"], adapters) for h in data["hosts"]}
        return {
            "round": data["round"],
            "plan": data,
            "plan_sha256": cases.sha256_file(Path(path)),
            "commit": at(repo),
            "kit": kit.digest(repo),
            **found,
            "adapters": {name: tracked_digest(Path(adapters) / name) for name in modules},
            "hosts": {h["adapter"]: {"version": version(modules[h["adapter"]], **containment),
                                     "model": h["model"]} for h in data["hosts"]},
        }
    except (CaseError, kit.KitError, contain.ContainmentError) as error:
        raise RoundError(f"{path}: {error}") from None


def write(record, store, repo=REPO):
    """Write a round's manifest to `store`, read it back and return its path. A round's manifest is written once:
    the same manifest again is kept, and a different one is refused."""
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    try:
        (kit.store_folder(store, repo) / record["round"]).mkdir(parents=True, exist_ok=True)
        folder = kit.store_folder(Path(store) / record["round"], repo)  # the round's folder, resolved, is outside too
    except kit.KitError as error:
        raise RoundError(str(error)) from None
    target = folder / MANIFEST
    fresh = folder / f".{MANIFEST}.{os.getpid()}"
    fresh.write_text(text)
    try:
        os.link(fresh, target)  # makes the manifest only where no entry has its name; it never replaces one
    except FileExistsError:
        pass
    finally:
        fresh.unlink()
    try:
        kept = manifest.kind(manifest.entry(target)) == "file" and target.read_bytes() == text.encode()
    except manifest.Unreadable:
        kept = False
    if not kept:  # read back, so another manifest, a link or a half-written file at its name is refused
        raise RoundError(f"{target}: round {record['round']} already has another manifest; a changed input is "
                         f"a new round")
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(prog="rounds.py", description="Plan an eval round.")
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan", help="write the round's manifest to the store")
    planning.add_argument("plan", help="the plan file")
    planning.add_argument("--store", required=True, help="the round store, outside the working tree")
    planning.add_argument("--host-path", action="append", default=[], dest="host_paths",
                          help="a host's install under the operator's home, which its jail may mount (repeatable)")
    running = commands.add_parser("run", help="take a planned round through its gates (gates.py)")
    running.add_argument("round", help="the round's name")
    running.add_argument("--store", required=True, help="the round store the round was planned in")
    running.add_argument("--host-path", action="append", default=[], dest="host_paths",
                         help="a host's install under the operator's home, which its jail may mount (repeatable)")
    running.add_argument("--seed", type=int, help="the seed that places the faults; a new one when not given")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            print(write(plan(args.plan, host_paths=args.host_paths), args.store))
        else:
            import gates  # it imports this module, so only when a round runs
            attempt = gates.run(args.store, args.round, seed=args.seed, host_paths=args.host_paths)
            print(json.dumps(attempt, indent=1, sort_keys=True))
    except RoundError as error:
        print(f"round: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
