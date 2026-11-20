"""The grade gate of a round (doc 11, Graders): what no check decided, answered by blind panels of graders, and
trusted only where the goldens were.

One rule: every page a round grades, each kept or made run's and each golden's, goes the same way, in one blind
order: the grader view, the page, a panel of two graders and a tie-breaker. A question is answered for a run only
when its expectation's goldens got their settled answers this round (`goldens.gate`); otherwise it stays ungraded
on that question, with why.

- Goldens: each case's goldens (`evals/goldens/<skill>/<case>/`, at the round's commit) are built as runs of the
  reference host (`reference`), checked with the round's check library, and asked what no check decided, as a run
  is (`goldens.bundle`).
- Panels: two graders on two different hosts when two hosts passed their probes, else two fresh graders on the
  one host, and a tie-breaker on the reference host (`grader.panel`). A grader runs the round's model of its host.
- Order: the pages of every run and golden are graded in the order the round's seed gives (`grader.blind`).
- Every page the gate grades leaves one record, written through the round's scrub to the attempt's own folder,
  `<store>/<round>/grades/<attempt>/runs/<key>.json` or `.../goldens/<skill>/<case>/<golden>.json`, so no attempt
  replaces another's: the hashes of the page and its questions, the questions asked, the panel's answers, those left
  unanswered, the agreement, and each grader's host, model, sheet, failed tries, refused messages and costs, the
  tie-breaker last. A golden's record adds its settled answers; a run's names its skill and case, keeps only its
  trusted answers and names the untrusted questions, with why.
- A run's grade is made once and kept across attempts (`KEPT`), whole, with the golden result its graders were
  trusted under (`trusted`), written only where none is, so a resumed round never sees a grade move under it. Each
  later grading rebuilds the run's page and refuses a kept grade of another page or questions; its goldens are
  graded again, and an answer counts only when its question is trusted both now and when the grade was made, so a
  grade whose graders lose trust is unscored. Goldens are never kept: every grading grades them, mixed in.
- The gate's outcome names, per case, each question some page was asked: None when its grading is trusted, or why
  not. A grader that breaks its jail, or a golden that cannot be built, stops the round.

Standard library only.
"""

import json
import tempfile

import checks
import evidence
import goldens
import grader
import grading
import view

REFERENCE = "claude-code"  # the reference host (doc 10, Hosts)
KEPT = "kept-grades"  # each run's grade, made once and kept across attempts: `<store>/<round>/kept-grades/<key>.json`


def reference(hosts):
    """The host that breaks ties and builds the goldens: the reference host when it passed its probes, else the
    first that did."""
    return REFERENCE if REFERENCE in hosts else sorted(hosts)[0]


def text(case, record, blob):
    """The page a grader reads of a bundle of `case`."""
    return grading.page(case.prompt, *view.view(record, blob))


def grade_gate(r):
    """The grade gate of the round `r` (`gates.Round`)."""
    return grade(r, r.runs, r.folder / "grades" / r.attempt)


def grade(r, made_runs, folder):
    """Grade the kept or made runs of `made_runs` with every golden mixed in, the goldens' records in `folder` and
    each run's in the attempt's own folder. A run with a kept grade (`KEPT`) is not graded again."""
    library, top = checks.library(r.repo / "evals" / "checks"), reference(r.hosts)
    pages, asked, sheets, case_of = {}, {}, {}, {}  # by page name: its text, its questions, its panel, its case
    kept = {}  # by run key: its kept grade, made once in an earlier grading
    for made in made_runs:
        if made["status"] in ("kept", "made") and r.asked[made["key"]]:
            record, blob = evidence.load(made["bundle"])
            pages[made["key"]] = text(r.cases[(made["skill"], made["case"])], record, blob)
            asked[made["key"]] = r.asked[made["key"]]
            case_of[made["key"]] = (made["skill"], made["case"])
            path = r.folder / KEPT / f"{made['key']}.json"
            if path.is_file():  # a kept grade is of this very page and questions, or the round stops
                kept[made["key"]] = json.loads(path.read_text())
                digest = grader.digest(pages[made["key"]], asked[made["key"]])
                if {name: kept[made["key"]].get(name) for name in digest} != digest:
                    raise ValueError(f"{path}: the kept grade is not of run {made['key']}'s page and questions")
    calibrated = {}  # (skill, case id): (case, its goldens)
    for (skill, case_id), case in r.cases.items():
        found = goldens.load(case, r.repo / "evals" / "goldens" / skill / case_id)
        calibrated[(skill, case_id)] = (case, found)
        for golden in found:
            with tempfile.TemporaryDirectory(prefix="hw-g-") as out:
                record, blobs = goldens.bundle(golden, case, r.modules[top], out, r.hosts[top]["drift"],
                                               r.record["hosts"][top]["version"]["version"], r.model(top),
                                               r.skills)
            bundle = checks.Bundle(record, blobs.__getitem__)
            verdicts = [checks.decide(e["check"]["name"], bundle, e["check"].get("args", {}), library)
                        if "check" in e else None for e in case.expectations]
            name = f"golden {skill}/{case_id}/{golden.name}"
            asked[name] = grading.questions(case.expectations, verdicts)
            if asked[name]:  # a golden whose every question a check decided has no page to grade
                pages[name], case_of[name] = text(case, record, blobs.__getitem__), (skill, case_id)
    panel, pair = _panel(r, top)
    for name, _ in grader.blind({name: page for name, page in pages.items() if name not in kept}, r.seed):
        sheets[name] = panel(pages[name], asked[name])
    outcome = {"goldens": {}, "runs": []}
    trusted = {}
    for (skill, case_id), (case, found) in calibrated.items():
        names = {golden.name: f"golden {skill}/{case_id}/{golden.name}" for golden in found}
        gate = goldens.gate(case, found, {golden.name: _graded(asked, sheets, names[golden.name])
                                          for golden in found})
        trusted[(skill, case_id)] = gate
        for golden in found:
            if names[golden.name] in sheets:
                r.write(_path(folder / "goldens" / skill / case_id, golden.name), {
                    **_record(pages[names[golden.name]], asked[names[golden.name]], sheets[names[golden.name]], pair,
                              top, r),
                    "settled": {q["id"]: golden.settled[q["id"]] for q in asked[names[golden.name]]}})
        ids = {q["id"] for name in pages if case_of[name] == (skill, case_id) for q in asked[name]}  # graded ones
        outcome["goldens"][f"{skill}/{case_id}"] = {id_: why for id_, why in gate.items() if id_ in ids}
    for made in made_runs:
        if made["key"] not in pages:
            continue
        doubted, ids = trusted[(made["skill"], made["case"])], [q["id"] for q in asked[made["key"]]]
        if made["key"] in kept:  # graded once: its graders must be trusted now and when it was made
            whole = kept[made["key"]]
            untrusted = {id_: doubted[id_] if doubted[id_] is not None else f"when graded: {whole['trusted'][id_]}"
                         for id_ in ids if doubted[id_] is not None or whole["trusted"][id_] is not None}
        else:
            whole = {**_record(pages[made["key"]], asked[made["key"]], sheets[made["key"]], pair, top, r),
                     "trusted": {id_: doubted[id_] for id_ in ids}, "attempt": r.attempt}
            r.write(_path(r.folder / KEPT, made["key"]), whole)  # made once, never replaced
            untrusted = {id_: doubted[id_] for id_ in ids if doubted[id_] is not None}
        record = {key: value for key, value in whole.items() if key not in ("trusted", "attempt")}
        record.update(answers={id_: answer for id_, answer in whole["answers"].items() if id_ not in untrusted},
                      untrusted=untrusted, case=f"{made['skill']}/{made['case']}", graded_in=whole["attempt"])
        r.write(_path(r.folder / "grades" / r.attempt / "runs", made["key"]), record)
        outcome["runs"].append({"key": made["key"], "answered": sorted(record["answers"]),
                                "unanswered": whole["unanswered"], "untrusted": sorted(untrusted),
                                "agreed": whole["agreed"], "asked": len(ids), "graded_in": whole["attempt"]})
    return outcome


def _path(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{name}.json"


def _record(page, asked, panel, pair, top, r):
    """What a page's panel found, as the store keeps it: the hashes of the page and its questions
    (`grader.digest`), the questions asked, the panel's answers, those left unanswered, the agreement, and each
    grader's host, model, sheet, failed tries, refused messages, the answers each refused sheet gave (`offered`) and
    each try's seconds and token counts, the tie-breaker last, with the questions a retry flipped (`flipped`)."""
    hosts = [*pair, top][:len(panel.graded)]
    return {**grader.digest(page, asked), "asked": [q["id"] for q in asked], "answers": panel.answers,
            "unanswered": panel.unanswered, "agreed": panel.agreed, "flipped": panel.flipped,
            "graders": [{"host": host, "model": r.model(host), "sheet": g.sheet, "tries": g.tries,
                         "refused": g.refused, "offered": g.offered, "costs": g.costs}
                        for host, g in zip(hosts, panel.graded)]}


def _graded(asked, sheets, name):
    """(the ids a golden was asked, the answers its panel gave), as `goldens.gate` reads them."""
    ids = [question["id"] for question in asked[name]]
    return ids, (sheets[name].answers if name in sheets else {})


def _panel(r, top):
    """The panel of the round, a function of (page, questions) that gives a `grader.Panel`, and its two hosts."""
    hosts = sorted(r.hosts)
    pair = hosts[:2] if len(hosts) > 1 else hosts * 2

    def one(host):
        def grade_one(page, questions):
            return r.grade(r.modules[host], page, questions, model=r.model(host), timeout=r.timeout,
                           **r.containment)
        return grade_one

    return (lambda page, questions: grader.panel(page, questions, [one(host) for host in pair], one(top))), pair
