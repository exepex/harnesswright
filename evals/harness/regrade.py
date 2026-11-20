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
- It writes `<store>/<round>/regrade/<pass>/` (doc 11, Cross-model grading): `regrade.json`, the pass and its
  routes, with a finish time that stays empty when the pass stopped; `pages.json`, each page by its place in the
  blind order, for the report, never for a grader; and per route `proved.json` and `pages/<place>.json`, each
  grader's sheet, tries, costs and logs. Everything passes the scrub of every containment the pass made.

Run from the repository root, at the round's commit:

    python3 evals/harness/regrade.py ROUND --store DIR --route ADAPTER=MODEL [--route ...] [--attempt NAME]
        [--seed N] [--pages all|run|golden] [--graders 1|2] [--host-path PATH ...]

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

sys.dont_write_bytecode = True  # its imports leave no bytecode in the kit's folder, which must hold only tracked files

import checks  # noqa: E402
import evidence  # noqa: E402
import faults  # noqa: E402
import gates  # noqa: E402
import goldens  # noqa: E402
import grader  # noqa: E402
import grader_faults  # noqa: E402
import grades  # noqa: E402
import grading  # noqa: E402
import labels  # noqa: E402
import prices  # noqa: E402
import probes  # noqa: E402
import rounds  # noqa: E402
import runs  # noqa: E402
from cases import REPO  # noqa: E402

TIMES = 2  # graders a route gives each page, unless the operator asks for fewer
KINDS = ("run", "golden")  # the pages a pass grades, unless the operator asks for one kind


class RegradeError(rounds.RoundError):
    """The pass cannot go on, and why."""


def route(text):
    """(adapter, model) of a route written `ADAPTER=MODEL`."""
    adapter, _, model = text.partition("=")
    if not (re.fullmatch(r"[a-z0-9-]+", adapter) and model):
        raise RegradeError(f"{text!r}: a route is ADAPTER=MODEL")
    return adapter, model


def folder_name(adapter, model):
    """A route's folder: its adapter and model, with every character a path or a shell could misread replaced, and
    the start of the hash of the route as written, so two routes never share a folder."""
    text = f"{adapter}={model}"
    return re.sub(r"[^A-Za-z0-9._-]", "_", text) + "-" + hashlib.sha256(text.encode()).hexdigest()[:12]


def source(r, attempt=None):
    """(name, {gate: outcome}) of the source attempt: `attempt`, or the latest whose grade gate passed."""
    found = {}
    for path in sorted((r.folder / "attempts").glob("*.json")):
        ran = {g["gate"]: g.get("outcome") for g in json.loads(path.read_text())["gates"] if g["passed"]}
        if "grade" in ran:
            found[path.stem] = ran
    named = attempt or max(found, default=None)
    if named not in found:
        raise RegradeError(f"round {r.record['round']}: no attempt {attempt or ''} whose grade gate passed")
    return named, found[named]


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


def pages(r, attempt, outcome):
    """{name: page} for every page the source attempt graded: its `text`, the questions `asked`, its `kind` (run or
    golden), `case`, the `host`, `model` and `arm` that made it, and a golden's `settled` answers. Each is rebuilt as
    the grade gate built it and must hash as its grade record says, or the pass stops. The run records must be
    exactly the runs the attempt graded (`outcome`, with its extra runs, `labels.with_extras`), and the golden
    records exactly the goldens its grade gate graded: each golden of the round's cases with a question no check
    decided."""
    graded, found = r.folder / "grades" / attempt, {}
    named = sorted(run["key"] for run in outcome["runs"])
    if sorted(path.stem for path in (graded / "runs").glob("*.json")) != named:
        raise RegradeError(f"attempt {attempt}: its run grade records are not the runs its grade gate graded")
    for path in sorted((graded / "runs").glob("*.json")):
        kept = json.loads(path.read_text())
        if not {"page", "questions", "case"} <= set(kept):
            raise RegradeError(f"run {path.stem}: graded before grade records kept page hashes; regrade a newer round")
        skill, case_id = kept["case"].split("/")
        bundle = runs.stored(runs.folder(r.record, r.store, path.stem, r.repo))
        if bundle is None or bundle[0] != "kept":
            raise RegradeError(f"run {path.stem}: its bundle is not in the store")
        record, blob = evidence.load(bundle[1])
        verdicts = json.loads((bundle[1].parent / "checks.json").read_text())["verdicts"]
        case = r.cases[(skill, case_id)]
        found[path.stem] = {"text": grades.text(case, record, blob), "kept": kept, "kind": "run", "case": kept["case"],
                            "host": record["host"], "model": record["model"], "arm": record["arm"],
                            "asked": grading.questions(case.expectations, verdicts)}
    top = grades.reference(r.hosts)
    library = checks.library(r.repo / "evals" / "checks")
    expected = set()  # the golden records the grade gate wrote: one for each golden with a question to grade
    for (skill, case_id), case in r.cases.items():
        for golden in goldens.load(case, r.repo / "evals" / "goldens" / skill / case_id):
            with tempfile.TemporaryDirectory(prefix="hw-g-") as out:
                record, blobs = goldens.bundle(golden, case, r.modules[top], out, r.hosts[top]["drift"],
                                               r.record["hosts"][top]["version"]["version"], r.model(top), r.skills)
            bundle = checks.Bundle(record, blobs.__getitem__)
            verdicts = [checks.decide(e["check"]["name"], bundle, e["check"].get("args", {}), library)
                        if "check" in e else None for e in case.expectations]
            asked = grading.questions(case.expectations, verdicts)
            if not asked:
                continue
            path = graded / "goldens" / skill / case_id / f"{golden.name}.json"
            expected.add(path)
            name = f"golden {skill}/{case_id}/{golden.name}"
            if not path.is_file():
                raise RegradeError(f"{name}: the grade gate graded it, and its grade record is not in the store")
            found[name] = {
                "text": grades.text(case, record, blobs.__getitem__), "kept": json.loads(path.read_text()),
                "kind": "golden", "case": f"{skill}/{case_id}", "host": top, "model": r.model(top), "arm": "golden",
                "settled": golden.settled, "asked": asked}
    if set((graded / "goldens").glob("*/*/*.json")) != expected:
        raise RegradeError(f"attempt {attempt}: its golden grade records are not the goldens its grade gate graded")
    for name, page in found.items():
        if not {"page", "questions"} <= set(page["kept"]):
            raise RegradeError(f"{name}: graded before grade records kept page hashes; regrade a newer round")
        if grader.digest(page["text"], page["asked"]) != {k: page["kept"].get(k) for k in ("page", "questions")}:
            raise RegradeError(f"{name}: the page rebuilt from the store is not the page the round graded")
    return found


def prove(r, module, model, tools, seed):
    """The probe and grader fault results of one route, under the round's kit: {"not run": reasons, "drift": the
    tools and drift record, "version": the host's version, "faults": each fault's place, whether it was caught and why
    not}. Every containment it made is kept for the scrub."""
    made = []
    with tempfile.TemporaryDirectory(prefix="hw-p-") as scratch:
        try:
            found = probes.probe_host(module, scratch, tools=tools, model=model, timeout=r.timeout, made=made,
                                      **r.containment)
        finally:
            r.keep(made)
    proved = {"not run": found["not run"], "drift": found["drift"], "version": None, "faults": []}
    if found["not run"]:
        return proved
    entries = [e for e in faults.load(r.repo / "evals" / "faults" / "harness.json")
               if e["id"] in grader_faults.PLANTS]
    case = r.cases[sorted(r.cases)[0]]
    version = proved["version"] = rounds.host_version(module, **r.containment)["version"]
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


def regrade(store, name, routes, attempt=None, repo=REPO, adapters=rounds.ADAPTERS, seed=None, kinds=KINDS,
            times=TIMES, **options):
    """Grade every page of round `name`'s source attempt again with each of `routes` ([(adapter, model)]): the pages
    of `kinds`, each by `times` fresh graders of each route. Return the pass's folder; raise RegradeError, scrubbed
    and after writing what it found, when anything stops the pass."""
    if len(set(routes)) != len(routes) or not routes:
        raise RegradeError("each route is given once, and at least one")
    if not (set(kinds) <= set(KINDS) and kinds) or times not in range(1, TIMES + 1):
        raise RegradeError(f"pages are some of {KINDS}, and graders 1 to {TIMES}")
    record = gates.read(store, name, repo)
    if rounds.commit(repo) != record["commit"]:
        raise RegradeError(f"{repo} is not at round {name}'s commit {record['commit']}")
    r = gates.Round(record, store, repo, adapters, seed=seed, **options)
    try:
        return _regrade(r, routes, attempt, adapters, kinds, times)
    except Exception as error:  # every way out passes the scrub of the containments the pass made
        if isinstance(error, RegradeError):
            raise RegradeError(r.quiet(str(error))) from None
        raise RegradeError(r.quiet(f"{type(error).__name__}: {error}")) from error


def _regrade(r, routes, attempt, adapters, kinds, times):
    same(r, adapters)
    attempt, outcome = source(r, attempt)
    passed = (outcome.get("probe") or {}).get("passed") or []  # the hosts the source attempt ran, as it built goldens
    r.hosts = {host: {"drift": json.loads((r.folder / "drift" / f"{host}.json").read_text())} for host in passed}
    graded = labels.with_extras({gate: {"passed": True, "outcome": found} for gate, found in outcome.items()})
    found = {page: built for page, built in pages(r, attempt, graded["grade"]["outcome"]).items()
             if built["kind"] in kinds}
    modules = {one: rounds.adapter(one[0], adapters) for one in routes}
    started = datetime.datetime.now(datetime.timezone.utc)
    (r.folder / "regrade").mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix=f"{started.strftime('%Y%m%dT%H%M%S')}-", dir=r.folder / "regrade"))
    # Each page's place in the blind order names its records: two pages of the same text, as a run and a golden
    # can be, share a blind id but not a place.
    order = [(page, f"{number:04d}") for number, (page, _) in
             enumerate(grader.blind({page: found[page]["text"] for page in found}, r.seed), start=1)]
    ids = dict(order)
    head = {"round": r.record["round"], "source": attempt, "commit": r.record["commit"], "kit": r.record["kit"],
            "seed": r.seed, "started": started.isoformat(timespec="seconds"), "finished": None,
            "pages": list(kinds), "graders": times, "tries": grader.TRIES, "timeout": r.timeout,
            "prompt": hashlib.sha256(grader.PROMPT.read_bytes()).hexdigest(), "prices": prices.load(r.repo)["date"],
            "routes": [{"adapter": one[0], "model": one[1], "folder": folder_name(*one),
                        "upstream": one[1].partition("@")[2] or None,  # the pinned one, when the route names it
                        "adapter_sha256": rounds.tracked_digest(Path(adapters) / one[0])} for one in routes]}
    r.write(out / "regrade.json", head)
    tools = sorted({tool for case in r.cases.values() for tool in case.tools})
    failed = []
    for one, entry in zip(routes, head["routes"]):
        (out / entry["folder"] / "pages").mkdir(parents=True)
        proved = prove(r, modules[one], one[1], tools, r.seed)
        entry["version"] = proved["version"]
        r.write(out / entry["folder"] / "proved.json", proved)
        if proved["not run"] or not proved["faults"] or not all(f["caught"] for f in proved["faults"]):
            failed.append(f"{one[0]}={one[1]}")
    r.write(out / "pages.json", {ids[page]: {
        **grader.digest(found[page]["text"], found[page]["asked"]), "name": page,
        **{k: found[page][k] for k in ("kind", "case", "host", "model", "arm")},
        "asked": [q["id"] for q in found[page]["asked"]], "settled": found[page].get("settled")} for page in found})
    r.write(out / "regrade.json", head)
    if failed:
        raise RegradeError(f"routes failed their probes or grader faults: {', '.join(failed)}; see {out}")
    kept = lambda contained, made, ran: r.keep([contained])  # noqa: E731  each grader's canaries, for the scrub
    for one, entry in zip(routes, head["routes"]):
        for page, id_ in order:
            graded = [r.grade(modules[one], found[page]["text"], found[page]["asked"], model=one[1],
                              timeout=r.timeout, watch=kept, **r.containment) for _ in range(times)]
            r.write(out / entry["folder"] / "pages" / f"{id_}.json", {
                **grader.digest(found[page]["text"], found[page]["asked"]),
                "graders": [{"sheet": g.sheet, "tries": g.tries, "refused": g.refused, "costs": g.costs, "logs": g.logs}
                            for g in graded]})
    head["finished"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    r.write(out / "regrade.json", head)  # a pass with no finish time stopped part way
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
    parser.add_argument("--pages", choices=("all",) + KINDS, default="all", help="which pages to grade (default all)")
    parser.add_argument("--graders", type=int, default=TIMES, help=f"graders per page and route (default {TIMES})")
    parser.add_argument("--host-path", action="append", default=[], dest="host_paths",
                        help="a host's install under the operator's home, which its jail may mount (repeatable)")
    args = parser.parse_args(argv)
    try:
        kinds = KINDS if args.pages == "all" else (args.pages,)
        print(regrade(args.store, args.round, args.routes, args.attempt, seed=args.seed, kinds=kinds,
                      times=args.graders, host_paths=args.host_paths))
    except rounds.RoundError as error:
        print(f"regrade: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
