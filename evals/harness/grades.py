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
- Each run's answers are written beside its bundle (`grades.json`): the panel's answers to the questions it was
  asked, those left unanswered, those not trusted this round with why, the agreement, and each grader's sheet and
  failed tries. A grader that breaks its jail, or a golden that cannot be built, stops the round.

Standard library only.
"""

import json
import tempfile
from pathlib import Path

import checks
import evidence
import goldens
import grader
import grading
import view

REFERENCE = "claude-code"  # the reference host (doc 10, Hosts)


def reference(hosts):
    """The host that breaks ties and builds the goldens: the reference host when it passed its probes, else the
    first that did."""
    return REFERENCE if REFERENCE in hosts else sorted(hosts)[0]


def text(record, blob):
    """The page a grader reads of a bundle."""
    return grading.page(*view.view(record, blob))


def grade_gate(r):
    """The grade gate of the round `r` (`gates.Round`)."""
    library, top = checks.library(r.repo / "evals" / "checks"), reference(r.hosts)
    pages, asked, sheets = {}, {}, {}  # by page name: its text, its questions, its panel
    for made in r.runs:
        if made["status"] in ("kept", "made") and r.asked[made["key"]]:
            record, blob = evidence.load(made["bundle"])
            pages[made["key"]], asked[made["key"]] = text(record, blob), r.asked[made["key"]]
    calibrated = {}  # (skill, case id): (case, its goldens)
    for (skill, case_id), case in r.cases.items():
        found = goldens.load(case, r.repo / "evals" / "goldens" / skill / case_id)
        calibrated[(skill, case_id)] = (case, found)
        for golden in found:
            with tempfile.TemporaryDirectory(prefix="hw-g-") as out:
                record, blobs = goldens.bundle(golden, case, r.modules[top], out, r.hosts[top]["drift"],
                                               r.record["hosts"][top]["version"]["version"], r.model(top),
                                               r.repo / "skills")
            bundle = checks.Bundle(record, blobs.__getitem__)
            verdicts = [checks.decide(e["check"]["name"], bundle, e["check"].get("args", {}), library)
                        if "check" in e else None for e in case.expectations]
            name = f"golden {skill}/{case_id}/{golden.name}"
            asked[name] = grading.questions(case.expectations, verdicts)
            if asked[name]:  # a golden whose every question a check decided has no page to grade
                pages[name] = text(record, blobs.__getitem__)
    panel = _panel(r, top)
    for name, _ in grader.blind(pages, r.seed):
        sheets[name] = panel(pages[name], asked[name])
    trusted = {}
    for (skill, case_id), (case, found) in calibrated.items():
        graded = {golden.name: _graded(asked, sheets, f"golden {skill}/{case_id}/{golden.name}") for golden in found}
        trusted[(skill, case_id)] = goldens.gate(case, found, graded)
    outcome = {"goldens": {f"{skill}/{case_id}": gate for (skill, case_id), gate in trusted.items()}, "runs": []}
    for made in r.runs:
        if made["key"] not in pages:
            continue
        doubted = trusted[(made["skill"], made["case"])]
        given = sheets[made["key"]]
        answers = {id_: answer for id_, answer in given.answers.items() if doubted[id_] is None}
        untrusted = {q["id"]: doubted[q["id"]] for q in asked[made["key"]] if doubted[q["id"]] is not None}
        found = {"answers": answers, "unanswered": given.unanswered, "untrusted": untrusted,
                 "agreed": given.agreed, "asked": given.asked,
                 "graders": [{"sheet": g.sheet, "tries": g.tries} for g in given.graded]}
        r.write(Path(made["bundle"]).parent / "grades.json", found)
        outcome["runs"].append({"key": made["key"], "answered": sorted(answers), "unanswered": given.unanswered,
                                "untrusted": sorted(untrusted), "agreed": given.agreed, "asked": given.asked})
    return outcome


def _graded(asked, sheets, name):
    """(the ids a golden was asked, the answers its panel gave), as `goldens.gate` reads them."""
    ids = [question["id"] for question in asked[name]]
    return ids, (sheets[name].answers if name in sheets else {})


def _panel(r, top):
    """The panel of the round: a function of (page, questions) that gives a `grader.Panel`."""
    hosts = sorted(r.hosts)
    pair = hosts[:2] if len(hosts) > 1 else hosts * 2

    def one(host):
        def grade_one(page, questions):
            return r.grade(r.modules[host], page, questions, model=r.model(host), timeout=r.timeout,
                           **r.containment)
        return grade_one

    return lambda page, questions: grader.panel(page, questions, [one(host) for host in pair], one(top))
