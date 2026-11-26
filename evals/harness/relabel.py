"""A relabel: the stored runs of a labelled round graded again under the kit as it is now, and labelled, with no
run made (doc 11, Relabel).

One rule: a relabel is a new attempt of a copy of the round, through the round's own gates, with the run gate
replaced by one that only finds the runs the labelled attempt kept (`found_gate`). Everything else is the round's:

- `copy` writes the copy to a new store, never the round's: the round's manifest, its drift records, each slot's
  folder as the run gate left it (its bundle, voids, tries not loaded and backstop matches), and that attempt's run
  gate outcome (`SOURCE`). Nothing graded, checked or labelled is copied (`CHECKED`), so the round's recorded
  results never change and no kept grade of an old page is reused (`grades.KEPT`).
- `kit check`: a judge approved the kit as it is now in the new store (`kit.check`). The repository may be at a
  later commit than the round's, but each case and skill the round ran must be as it was at the round's commit,
  save the fields of `GRADING_ONLY`, which shape a grader's page and never a run: every run is then a run of the
  case it is graded on.
  That check is the only one of a relabel's cases: it covers the plan's `fault_case` too, so the faults gate takes
  the fault case as it now is (`faults_gate`) instead of checking its hash at the round's commit again.
- `lint`, `probe`, `faults`, `check`, `grade` and `label` are the round's gates. The probe gate keeps the round's
  drift records and stops on other tools.
- The extra runs gate makes runs, so a relabel has none, and a measure that is too close stays too close.

Run from the repository root, at a clean commit:

    python3 evals/harness/relabel.py copy ROUND --from STORE --attempt ATTEMPT --to NEW_STORE
    python3 evals/harness/relabel.py run ROUND --store NEW_STORE [--host-path PATH ...] [--seed N]

Standard library only.
"""

import argparse
import copy as copying
import json
import shutil
import sys

import evidence
import gates
import grades
import kit
import labels
import rounds
import runs
from cases import REPO, Case

CHECKED = "checks.json"  # a slot's check verdicts (`gates.check_one`), the one file of a slot a relabel makes again
SOURCE = "relabel.json"  # in the copy's round folder: where it came from, and the run gate outcome it relabels
GRADING_ONLY = ("reads_final_message",)  # the case fields a relabel may find changed: none shapes a run


class RelabelError(rounds.RoundError):
    """A relabel that cannot be made, with the reason."""


def copy(source, name, attempt, target, repo=REPO):
    """Copy round `name` of store `source`, as its labelled attempt `attempt` left it, to the store `target`."""
    old, new = kit.store_folder(source, repo) / name, kit.store_folder(target, repo) / name
    if new.exists() or new.is_symlink():
        raise RelabelError(f"{new}: a relabel is copied to a new folder")
    if not (old / "labels" / f"{attempt}.json").is_file():
        raise RelabelError(f"round {name}, attempt {attempt}: no labels, so nothing to relabel")
    found = {g["gate"]: g for g in json.loads((old / "attempts" / f"{attempt}.json").read_text())["gates"]}
    if found.get("extra runs", {}).get("outcome", {}).get("passes"):
        raise RelabelError(f"round {name}, attempt {attempt}: it made extra runs, which a relabel does not grade")
    made = found["run"]["outcome"]
    new.mkdir(parents=True)
    shutil.copy2(old / rounds.MANIFEST, new / rounds.MANIFEST)
    shutil.copytree(old / "drift", new / "drift", symlinks=True)
    for run in made:  # each slot as the run gate left it, its voids and tries not loaded too
        slot = old / "runs" / run["key"]
        if slot.is_dir():  # all but the check gate's verdicts, which the relabel makes again
            shutil.copytree(slot, new / "runs" / run["key"], symlinks=True, ignore=lambda folder, names, top=str(
                slot): [CHECKED] if folder == top and CHECKED in names else [])
    (new / SOURCE).write_text(json.dumps({"from": str(old), "attempt": attempt, "run": made}, indent=1,
                                         sort_keys=True) + "\n")
    return new


def kit_check(r):
    """The kit check of a relabel: the kit as it is now, approved in the copy's store, and each case and skill of
    the round as it was at the round's commit (`same`)."""
    same(r)
    return {"approved": kit.check(r.store, r.repo), "runs' kit": r.record["kit"], "runs' commit": r.record["commit"]}


def same(r):
    """Raise RelabelError unless each case and skill of round `r`, and its `fault_case`, is as it was at the round's
    commit, save the fields of `GRADING_ONLY` in each `case.json`."""
    commit, problems = r.record["commit"], []
    cases, skill_folders = held(r)
    for case in cases:
        folder = case.folder.relative_to(r.repo)
        for path in rounds._git(r.repo, "diff", "--name-only", commit, "--", str(folder)).splitlines():
            if path != f"{folder}/case.json":
                problems.append(path)
                continue
            then = json.loads(rounds._git(r.repo, "show", f"{commit}:{path}"))
            now = json.loads((r.repo / path).read_text())
            if {k: v for k, v in then.items() if k not in GRADING_ONLY} != {
                    k: v for k, v in now.items() if k not in GRADING_ONLY}:
                problems.append(path)
    for name, folder in skill_folders.items():
        if folder is None:
            problems.append(f"{name}: no folder")
            continue
        problems += rounds._git(r.repo, "diff", "--name-only", commit, "--",
                                str(folder.relative_to(r.repo))).splitlines()
    if problems:
        raise RelabelError(f"changed since the round's commit {commit}, so its runs are not of them: "
                           f"{', '.join(problems)}")


def held(r):
    """What round `r` holds to its commit, read from its record one way: its cases and the plan's fault case, when
    it names one (`fault_case`), and {name: folder, or None when it has none} of each skill it records."""
    fault = fault_case(r)
    return [case for _, case in sorted(r.cases.items())] + [fault] * (fault is not None), {
        name: r.skills.get(name) for name in sorted(r.record["skills"])}


def fault_case(r):
    """The plan's `fault_case` of round `r`, as the repository holds it now, or None when the plan names none."""
    chosen = r.record.get("fault_case")
    if chosen is None:
        return None
    return Case(r.repo / "evals" / "skills" / chosen["skill"] / "cases" / chosen["case"], chosen["skill"])


def faults_gate(r):
    """The round's faults gate, on the plan's `fault_case` as it now is: `same`, the one check of a relabel's cases,
    proved it the round's."""
    fault = fault_case(r)
    if fault is not None:
        r = copying.copy(r)  # the gate reads the record alone; the manifest is never written
        r.record = {**r.record, "fault_case": {**r.record["fault_case"], "sha256": fault.sha256}}
    return gates.faults_gate(r)


def found_gate(r):
    """The run gate of a relabel: each slot as the labelled attempt's run gate gave it, each kept or made run found
    in the copy's store, none made."""
    reported = []
    for made in json.loads((r.folder / SOURCE).read_text())["run"]:
        bundle = None
        if made["status"] in ("kept", "made"):
            try:
                found = runs.stored(r.folder / "runs" / made["key"])
            except (evidence.EvidenceError, OSError, ValueError):  # a bundle a blob or its record is missing from
                found = None
            if not found or found[0] != "kept":
                raise gates.Stop(f"run {made['key']}: its bundle is not in the store", reported)
            made, bundle = {**made, "status": "kept"}, str(found[1])
        reported.append(made)
        r.runs.append({**made, "bundle": bundle})
    return reported


GATES = (("kit check", kit_check), ("lint", gates.lint_gate), ("probe", gates.probe_gate),
         ("faults", faults_gate), ("run", found_gate), ("check", gates.check_gate),
         ("grade", grades.grade_gate), ("label", labels.label_gate))


def run(store, name, repo=REPO, **options):
    """Take the relabel of round `name` in the copy's store `store` through `GATES`; return the attempt record."""
    if not (kit.store_folder(store, repo) / name / SOURCE).is_file():
        raise RelabelError(f"{store}: round {name} is not a relabel's copy; copy it first")
    return gates.run(store, name, repo, gates=GATES, at=rounds.commit(repo), **options)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="relabel.py", description="Grade a labelled round's runs again.")
    commands = parser.add_subparsers(dest="command", required=True)
    copying = commands.add_parser("copy", help="copy a labelled round's runs to a new store")
    copying.add_argument("round")
    copying.add_argument("--from", required=True, dest="source", help="the round's store")
    copying.add_argument("--attempt", required=True, help="the labelled attempt whose runs are relabelled")
    copying.add_argument("--to", required=True, dest="target", help="the new store, outside the working tree")
    running = commands.add_parser("run", help="take the copy through the relabel's gates")
    running.add_argument("round")
    running.add_argument("--store", required=True, help="the new store the round was copied to")
    running.add_argument("--host-path", action="append", default=[], dest="host_paths",
                         help="a host's install under the operator's home, which its jail may mount (repeatable)")
    running.add_argument("--seed", type=int, help="the seed that places the faults; a new one when not given")
    args = parser.parse_args(argv)
    try:
        if args.command == "copy":
            print(copy(args.source, args.round, args.attempt, args.target))
        else:
            attempt = run(args.store, args.round, seed=args.seed, host_paths=args.host_paths)
            print(json.dumps(attempt, indent=1, sort_keys=True))
    except (rounds.RoundError, kit.KitError, OSError, ValueError) as error:
        print(f"relabel: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
