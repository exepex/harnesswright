"""Grading faults: the planted faults of grading (doc 11, Harness faults), by the rule of `faults.py`: each is planted
from its catalogue entry at a place a seed chooses, its own gate runs unchanged, and only the one outcome it names
counts as caught.

One rule for their material: every grading fault is planted on the goldens of one case of the repository, chosen by
the seed, each made a bundle on the setup's host as a run is (`goldens.bundle`), with its page and the questions
its checks leave to graders. So a grading fault meets real pages and real questions, never ones made for it. The
graders here are planted: each answers as its fault says, and the harness's own sheet check, view, panel and golden
gate decide.

- `sheet`: one answer of a correct sheet left out, given twice, given for a question not asked, not yes or no,
  quoting what the page does not hold, or holding another field. The sheet check (`grading.check`) must refuse it
  for that reason, and accept the same sheet without the plant.
- `golden`: graders that answer `yes` to everything, `no` to everything, or one question of one golden wrong. The
  golden gate (`goldens.gate`) must stop trusting exactly the questions whose settled answer they missed, and trust
  the rest it trusts when graders give every settled answer.
- `tie`: two graders that answer one question or every question two ways, or one grader with no sheet. A fresh
  grader must be asked exactly the split questions and decide them; with one grader ungraded, no question is
  answered and no fresh grader is asked, so one grader never decides alone (`grader.panel`).
- `view`: the arm, or the skill's name and path, put in a record's arm, final message, log or files. The page a
  grader reads (`view.view`, `grading.page`) must name none of them.

Standard library only.
"""

import copy
import shutil

import cases
import checks
import goldens
import grader
import grading
import view
from faults import Missed

SHEET = {"left out": "not answered", "twice": "is answered twice", "stranger": "is not a question of this run",
         "not yes or no": "is not yes or no", "misquoted": "not found word for word", "extra field": "nothing else"}
WRONG = {"all yes": lambda settled: "yes", "all no": lambda settled: "no",
         "one flipped": lambda settled: _flip(settled)}


def _flip(answer):
    return "no" if answer == "yes" else "yes"


def _pages(setup, rng):
    """(case, [(golden, record, blob, asked)]) for the goldens of the repository case the seed chooses."""
    found = [(s.name, c.name) for s in sorted(goldens.ROOT.glob("*")) if s.is_dir() for c in sorted(s.iterdir())]
    if not found:
        raise Missed("the repository has no goldens to plant grading faults on")
    skill, name = rng.choice(found)
    [case] = [c for c in cases.load_cases(skill) if c.id == name]
    pages = []
    for golden in goldens.load(case):
        out = setup.folder()
        try:
            record, blobs = goldens.bundle(golden, case, setup.adapter, out, setup.drift, setup.host_version,
                                           setup.model)
        finally:
            shutil.rmtree(out, ignore_errors=True)
        bundle = checks.Bundle(record, blobs.__getitem__)
        verdicts = [checks.decide(e["check"]["name"], bundle, e["check"].get("args", {})) if "check" in e else None
                    for e in case.expectations]
        pages.append((golden, record, blobs.__getitem__, grading.questions(case.expectations, verdicts)))
    return case, pages


def _text(record, blob):
    return grading.page(*view.view(record, blob))


def _sheet(page, asked, answer):
    """A sheet answering each question of `asked` by `answer(id)`, each quoting the page's first line."""
    quote = next(line for line in page.splitlines() if line.strip())
    return {"answers": [{"id": q["id"], "answer": answer(q["id"]), "evidence": quote} for q in asked]}


def _grader(answer, calls=None):
    """A planted grader: it answers each question by `answer(id)`, or gives no sheet when `answer` is None, and
    records the ids it was asked in `calls`."""
    def grade_one(page, asked):
        if calls is not None:
            calls.append([question["id"] for question in asked])
        if answer is None:
            return grader.Graded(None, ["the host failed: planted"], [[]])
        return grader.Graded(_sheet(page, asked, answer), [], [[]])
    return grade_one


def sheet(setup, fault, rng, place):
    """A correct sheet of one golden's page with one fault at `place`. Caught when the sheet check accepts the
    sheet and refuses the planted one for the reason the place names."""
    _, pages = _pages(setup, rng)
    golden, record, blob, asked = rng.choice([p for p in pages if p[3]])
    page, ids = _text(record, blob), [question["id"] for question in asked]
    clean = _sheet(page, asked, golden.settled.get)
    problems = grading.check(clean, ids, page)
    if problems:
        return f"the sheet check refused the clean sheet: {problems}"
    answers, pick = clean["answers"], rng.randrange(len(clean["answers"]))
    one, before, after = answers[pick], answers[:pick], answers[pick + 1:]
    changed = {"not yes or no": {**one, "answer": rng.choice(("maybe", "unknown", "Yes"))},
               "misquoted": {**one, "evidence": f"hw-{rng.getrandbits(32):08x} says so"},
               "extra field": {**one, "confidence": "high"}}
    planted = {"left out": before + after, "twice": answers + [one],
               "stranger": answers + [{**one, "id": f"q{len(ids) + 100}"}]}.get(place)
    planted = planted if planted is not None else before + [changed[place]] + after
    problems = grading.check({"answers": planted}, ids, page)
    if not any(SHEET[place] in problem for problem in problems):
        return f"the sheet check did not refuse it as {SHEET[place]!r}: {problems}"
    return None


def _gate(case, pages, answer):
    """The golden gate on `pages` graded by a panel of two planted graders that both answer by `answer(golden, id)`."""
    graded = {}
    for golden, record, blob, asked in pages:
        one = _grader(lambda id_, golden=golden: answer(golden, id_))
        found = grader.panel(_text(record, blob), asked, [one, one], _grader(None))
        graded[golden.name] = ([question["id"] for question in asked], found.answers)
    return goldens.gate(case, [p[0] for p in pages], graded)


def golden(setup, fault, rng, place):
    """Graders that miss settled answers as `place` says. Caught when the gate, which trusts a set of questions when
    graders give every settled answer, stops trusting exactly those of them whose settled answer was missed."""
    case, pages = _pages(setup, rng)
    trusted = [id_ for id_, why in _gate(case, pages, lambda g, id_: g.settled[id_]).items() if why is None]
    if not trusted:
        return "the gate trusts no question even when graders give every settled answer"
    asked = [(g.name, q["id"]) for g, _, _, questions in pages for q in questions if q["id"] in trusted]
    target = rng.choice(asked)
    if place == "one flipped":
        wrong = lambda g, id_: _flip(g.settled[id_]) if (g.name, id_) == target else g.settled[id_]
    else:
        wrong = lambda g, id_: WRONG[place](g.settled[id_])
    by_name = {p[0].name: p[0] for p in pages}
    missed = {id_ for name, id_ in asked if wrong(by_name[name], id_) != by_name[name].settled[id_]}
    found = _gate(case, pages, wrong)
    flagged = {id_ for id_ in trusted if found[id_] is not None}
    if flagged != missed:
        return f"the gate stopped trusting {sorted(flagged)}, not the missed {sorted(missed)}"
    return None


def tie(setup, fault, rng, place):
    """Two graders of one page that split as `place` says, and a fresh tie-breaker giving the settled answers."""
    _, pages = _pages(setup, rng)
    golden, record, blob, asked = rng.choice([p for p in pages if p[3]])
    ids, settled = [question["id"] for question in asked], golden.settled
    split = {"one split": {rng.choice(ids)}, "all split": set(ids), "one ungraded": set()}[place]
    second = None if place == "one ungraded" else (lambda id_: _flip(settled[id_]) if id_ in split else settled[id_])
    calls = []
    found = grader.panel(_text(record, blob), asked, [_grader(settled.get), _grader(second)],
                         _grader(settled.get, calls))
    if place == "one ungraded":
        if calls or found.answers or found.unanswered != ids:
            return f"one grader decided alone: tie-breaker asked {calls}, answers {found.answers}"
        return None
    want = {id_: settled[id_] for id_ in ids}
    if calls != [[id_ for id_ in ids if id_ in split]] or found.answers != want or found.unanswered:
        return f"the tie-breaker was asked {calls}, not the split {sorted(split)}, and gave {found.answers}"
    return None


def view_(setup, fault, rng, place):
    """The arm, or the skill's name and one of its paths, put in one golden's record at `place`. Caught when the page
    of the clean record names none of them and the page of the planted record names none either."""
    _, pages = _pages(setup, rng)
    _, record, blob, _ = rng.choice(pages)
    layer = record["overlay"]
    path = rng.choice(layer["paths"])
    names = [layer["skill"], path, "with_skill", "without_skill"]
    planted = copy.deepcopy(record)
    if place == "arm":
        planted["arm"] = "with_skill"
    elif place == "message":
        planted["final_message"] = f"{planted['final_message'] or ''}\nI followed {path}/SKILL.md ({layer['skill']}).\n"
    elif place == "command":
        planted["log"].insert(0, {"kind": "command", "source": "observed", "command": f"cat {path}/SKILL.md",
                                  "output": f"# {layer['skill']}\n", "exit_code": 0})
    else:
        planted["files_after"][f"{path}/SKILL.md"] = next(iter(record["files_after"].values()))
    clean = _text(record, blob)
    if any(name in clean for name in names):
        return "the clean page already names the arm or the skill, so the plant proves nothing"
    shown = [name for name in names if name in _text(planted, blob)]
    if shown:
        return f"the page a grader reads names {shown}"
    return None


PLANTS = {
    "sheet": (sheet, tuple(SHEET), False),
    "golden": (golden, tuple(WRONG), False),
    "tie": (tie, ("one split", "all split", "one ungraded"), False),
    "view": (view_, ("arm", "message", "command", "file"), False),
}
