"""Cross-model grading (doc 11, Cross-model grading): every page a finished round graded, graded again by each
grader route, an adapter and a model, for the comparison report. A measurement, not a gate: it gives no label, and
it never changes the round's grades or labels.

One rule: every route grades through the round's own path, `grader.grade` in the jail, under the round's approved
kit, on the round's own pages. So the pass refuses a round whose kit is not the approved one, a repository that is
not at the round's commit, an adapter of the round that has changed, and a case that has changed; it rebuilds every
page from the stored bundles with the round's code, as the grade gate built it, and grades a page only when the page
and its questions hash to what the round's grade record kept (`grader.digest`). Before any route grades, each one
passes every probe and the grader faults (`grader_faults.py`), as a round's hosts do; one that fails stops the pass.

- The source is one attempt of the round, the latest whose grade gate passed unless another is named: its grade
  records name the pages, `grades/<attempt>/runs/<key>.json` and `.../goldens/<skill>/<case>/<golden>.json`.
- Each route grades every page twice, two fresh graders, in the blind order of the pass's seed. Nothing of the
  round's panel is read.
- It writes `<store>/<round>/regrade/<pass>/`: `regrade.json` (the round, the source attempt, the commit, the kit,
  the seed, the prompt's hash, the price file's date and the routes), `pages.json` (each page's place, hashes, kind,
  case, the host, model and arm that made it, and a golden's settled answers: for the report, never for a grader),
  and a folder per route with its probe and fault results (`proved.json`) and one record per page
  (`pages/<place>.json`, by the page's place in the blind order: each grader's sheet, failed tries, seconds and
  token counts by model). Everything passes the scrub of every containment the pass made.

Run from the repository root, at the round's commit:

    python3 evals/harness/regrade.py ROUND --store DIR --route ADAPTER=MODEL [--route ...] [--attempt NAME]
        [--seed N] [--host-path PATH ...]

Standard library only.
"""

import argparse
import datetime
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

import checks
import evidence
import faults
import gates
import goldens
import grader
import grader_faults
import grades
import grading
import prices
import probes
import rounds
import runs
from cases import REPO

TIMES = 2  # graders a route gives each page


class RegradeError(rounds.RoundError):
    """The pass cannot go on, and why."""


def route(text):
    """(adapter, model) of a route written `ADAPTER=MODEL`."""
    adapter, _, model = text.partition("=")
    if not (re.fullmatch(r"[a-z0-9-]+", adapter) and model):
        raise RegradeError(f"{text!r}: a route is ADAPTER=MODEL")
    return adapter, model


def folder_name(adapter, model):
    """A route's folder: its adapter and model, with every character a path or a shell could misread replaced."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", f"{adapter}={model}")


def source(r, attempt=None):
    """The name of the source attempt: `attempt`, or the latest whose grade gate passed."""
    found = {}
    for path in sorted((r.folder / "attempts").glob("*.json")):
        gates_ran = json.loads(path.read_text())["gates"]
        found[path.stem] = any(g["gate"] == "grade" and g["passed"] for g in gates_ran)
    named = attempt or max((name for name, graded in found.items() if graded), default=None)
    if named is None or not found.get(named):
        raise RegradeError(f"round {r.record['round']}: no attempt {attempt or ''} whose grade gate passed".strip())
    return named


def same(r, adapters):
    """Raise unless the kit is the approved one the manifest hashed, and every case and adapter of the round is as
    the manifest hashed it."""
    gates.kit_check(r)
    changed = [f"{skill}/{case_id}" for (skill, case_id), case in r.cases.items()
               if case.sha256 != r.record["cases"][skill][case_id]]
    changed += [f"adapter {name}" for name, digest in r.record["adapters"].items()
                if rounds.tracked_digest(Path(adapters) / name) != digest]
    if changed:
        raise RegradeError(f"changed since the round: {', '.join(changed)}")


def pages(r, attempt):
    """{name: page} for every page the source attempt graded: its `text`, the questions `asked`, its `kind` (run or
    golden), `case`, the `host`, `model` and `arm` that made it, and a golden's `settled` answers. Each is rebuilt as
    the grade gate built it and must hash as its grade record says, or the pass stops."""
    graded, found = r.folder / "grades" / attempt, {}
    for path in sorted((graded / "runs").glob("*.json")):
        kept = json.loads(path.read_text())
        skill, case_id = kept["case"].split("/")
        bundle = runs.stored(runs.folder(r.record, r.store, path.stem, r.repo))
        if bundle is None or bundle[0] != "kept":
            raise RegradeError(f"run {path.stem}: its bundle is not in the store")
        record, blob = evidence.load(bundle[1])
        verdicts = json.loads((bundle[1].parent / "checks.json").read_text())["verdicts"]
        found[path.stem] = {"text": grades.text(record, blob), "kept": kept, "kind": "run", "case": kept["case"],
                            "host": record["host"], "model": record["model"], "arm": record["arm"],
                            "asked": grading.questions(r.cases[(skill, case_id)].expectations, verdicts)}
    top = grades.reference(r.hosts)
    library = checks.library(r.repo / "evals" / "checks")
    for path in sorted((graded / "goldens").glob("*/*/*.json")):
        skill, case_id, name = path.parent.parent.name, path.parent.name, path.stem
        case = r.cases[(skill, case_id)]
        [golden] = [g for g in goldens.load(case, r.repo / "evals" / "goldens" / skill / case_id) if g.name == name]
        with tempfile.TemporaryDirectory(prefix="hw-g-") as out:
            record, blobs = goldens.bundle(golden, case, r.modules[top], out, r.hosts[top]["drift"],
                                           r.record["hosts"][top]["version"]["version"], r.model(top), r.skills)
        bundle = checks.Bundle(record, blobs.__getitem__)
        verdicts = [checks.decide(e["check"]["name"], bundle, e["check"].get("args", {}), library)
                    if "check" in e else None for e in case.expectations]
        found[f"golden {skill}/{case_id}/{name}"] = {
            "text": grades.text(record, blobs.__getitem__), "kept": json.loads(path.read_text()), "kind": "golden",
            "case": f"{skill}/{case_id}", "host": top, "model": r.model(top), "arm": "golden",
            "settled": golden.settled, "asked": grading.questions(case.expectations, verdicts)}
    for name, page in found.items():
        if grader.digest(page["text"], page["asked"]) != {k: page["kept"].get(k) for k in ("page", "questions")}:
            raise RegradeError(f"{name}: the page rebuilt from the store is not the page the round graded")
    return found


def prove(r, module, model, tools, seed):
    """The probe and grader fault results of one route, under the round's kit: {"not run": reasons, "faults": each
    fault's place, whether it was caught and why not}. Every containment it made is kept for the scrub."""
    made = []
    with tempfile.TemporaryDirectory(prefix="hw-p-") as scratch:
        try:
            found = probes.probe_host(module, scratch, tools=tools, model=model, timeout=r.timeout, made=made,
                                      **r.containment)
        finally:
            r.keep(made)
    proved = {"not run": found["not run"], "faults": []}
    if found["not run"]:
        return proved
    entries = [e for e in faults.load(r.repo / "evals" / "faults" / "harness.json")
               if e["id"] in grader_faults.PLANTS]
    case = r.cases[sorted(r.cases)[0]]
    version = rounds.host_version(module, **r.containment)["version"]
    with tempfile.TemporaryDirectory(prefix="hw-f-") as scratch:
        setup = faults.Setup(module, case, r.skills, scratch, found["drift"], model=model, host_version=version,
                             timeout=r.timeout, repo=r.repo, **r.containment)
        try:
            for entry in entries:
                for place in grader_faults.PLANTS[entry["id"]][1]:
                    result = faults.run(entry, setup, f"{seed}:{entry['id']}:{place}", place)
                    proved["faults"].append({k: result[k] for k in ("id", "place", "caught", "reason")})
        finally:
            r.keep(setup.made)
    return proved


def regrade(store, name, routes, attempt=None, repo=REPO, adapters=rounds.ADAPTERS, seed=None, **options):
    """Grade every page of round `name`'s source attempt again with each of `routes` ([(adapter, model)]). Return
    the pass's folder; raise RegradeError, after writing what it found, when a route fails its probes or faults."""
    record = gates.read(store, name, repo)
    if rounds.commit(repo) != record["commit"]:
        raise RegradeError(f"{repo} is not at round {name}'s commit {record['commit']}")
    r = gates.Round(record, store, repo, adapters, seed=seed, **options)
    same(r, adapters)
    attempt = source(r, attempt)
    r.hosts = {host: {"drift": json.loads((r.folder / "drift" / f"{host}.json").read_text())}
               for host in record["hosts"] if (r.folder / "drift" / f"{host}.json").is_file()}
    found = pages(r, attempt)
    started = datetime.datetime.now(datetime.timezone.utc)
    (r.folder / "regrade").mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix=f"{started.strftime('%Y%m%dT%H%M%S')}-", dir=r.folder / "regrade"))
    # Each page's place in the blind order names its records: two pages of the same text, as a run and a golden
    # can be, share a blind id but not a place.
    order = [(page, f"{number:04d}") for number, (page, _) in
             enumerate(grader.blind({page: found[page]["text"] for page in found}, r.seed), start=1)]
    ids = dict(order)
    r.write(out / "regrade.json", {
        "round": name, "source": attempt, "commit": record["commit"], "kit": record["kit"], "seed": r.seed,
        "started": started.isoformat(timespec="seconds"), "routes": [list(one) for one in routes],
        "prompt": hashlib.sha256(grader.PROMPT.read_bytes()).hexdigest(),
        "prices": prices.load(r.repo)["date"]})
    r.write(out / "pages.json", {ids[page]: {
        **grader.digest(found[page]["text"], found[page]["asked"]), "name": page,
        **{k: found[page][k] for k in ("kind", "case", "host", "model", "arm")},
        "asked": [q["id"] for q in found[page]["asked"]], "settled": found[page].get("settled")} for page in found})
    tools = sorted({tool for case in r.cases.values() for tool in case.tools})
    modules = {one: rounds.adapter(one[0], adapters) for one in routes}
    failed = []
    for one in routes:
        (out / folder_name(*one) / "pages").mkdir(parents=True)
        proved = prove(r, modules[one], one[1], tools, r.seed)
        r.write(out / folder_name(*one) / "proved.json", proved)
        if proved["not run"] or not all(f["caught"] for f in proved["faults"]):
            failed.append(f"{one[0]}={one[1]}")
    if failed:
        raise RegradeError(f"routes failed their probes or grader faults: {', '.join(failed)}; see {out}")
    for one in routes:
        for page, id_ in order:
            graded = [r.grade(modules[one], found[page]["text"], found[page]["asked"], model=one[1],
                              timeout=r.timeout, **r.containment) for _ in range(TIMES)]
            r.write(out / folder_name(*one) / "pages" / f"{id_}.json", {
                **grader.digest(found[page]["text"], found[page]["asked"]),
                "graders": [{"sheet": g.sheet, "tries": g.tries, "costs": g.costs} for g in graded]})
    return out


def _route(text):
    try:
        return route(text)
    except RegradeError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def main(argv=None):
    parser = argparse.ArgumentParser(prog="regrade.py", description="Grade a finished round again, per route.")
    parser.add_argument("round", help="the round's name")
    parser.add_argument("--store", required=True, help="the round store the round ran in")
    parser.add_argument("--route", action="append", required=True, dest="routes", type=_route,
                        help="a grader route, ADAPTER=MODEL (repeatable)")
    parser.add_argument("--attempt", help="the source attempt; the latest whose grade gate passed when not given")
    parser.add_argument("--seed", type=int, help="the seed of the blind order; a new one when not given")
    parser.add_argument("--host-path", action="append", default=[], dest="host_paths",
                        help="a host's install under the operator's home, which its jail may mount (repeatable)")
    args = parser.parse_args(argv)
    try:
        print(regrade(args.store, args.round, args.routes, args.attempt, seed=args.seed,
                      host_paths=args.host_paths))
    except rounds.RoundError as error:
        print(f"regrade: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
