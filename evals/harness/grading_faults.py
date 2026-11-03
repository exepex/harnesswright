"""Grading faults: the planted faults of grading (doc 11, Harness faults), by the rule of `faults.py`: each is planted
from its catalogue entry at a place a seed chooses, its own gate runs unchanged, and only the one outcome it names
counts as caught.

Two rules. Every grading fault is planted on the goldens of one case of the repository, chosen by the seed, each
made a bundle on the setup's host as a run is (`goldens.bundle`), with the questions its checks leave to graders,
so it meets real pages and real questions. And a plant covers every value of every choice its gate depends on:
every answer of a sheet with both values, every bad word, every golden and question, both sides, both graders,
every place a name can be carried. The seed chooses only the case, the page and the order, so a gate that skips any
one part misses the fault at every seed, never only at the seeds that happen to pick that part.

- `sheet`: each answer of a correct sheet in turn, as `yes` and as `no`, left out, given twice, not yes or no (every
  word of WORDS), quoting what the page does not hold, quoting nothing, or holding another field (as the file
  itself may), and a question not asked answered. The sheet check (`grading.check`) must refuse every planted
  sheet for that reason, and accept the sheet without the plant.
- `golden`: graders that answer `yes` to everything or `no` to everything, that answer one question of one golden
  wrong (each in turn), or that leave one golden unanswered (each in turn); and right graders on goldens that settle
  a question one way only (each question, each way). The golden gate (`goldens.gate`) must stop trusting exactly
  the questions whose settled answer was missed, or that are no longer settled both ways, and trust the rest it
  trusts when graders give every settled answer on every golden.
- `tie`: two graders that answer one question (each in turn) or every question two ways, or one grader with no
  sheet. A fresh
  grader must be asked exactly the split questions, and its answer, which sides with each grader on some question,
  must decide them; with one grader ungraded no question is answered and no fresh grader is asked, so one grader
  never decides alone (`grader.panel`).
- `view`: the arm, or the skill's name and each of its paths on lines of their own, put in a record's arm, final
  message, every kind of log entry, or files and changes (a file on each path, a link to one, and lines in a world
  file's text). Neither the view (`view.view`, its record and every blob) nor the page (`grading.page`) may name
  any of them, and the clean ones name none. And the planted view and page must equal those of a control, the same
  record without the plant's actions on the overlay and its lines that name the skill: a tell with its names taken
  out, such as an empty skill-load entry, still shows.

Standard library only.
"""

import copy
import hashlib
import json
import shutil

import cases
import checks
import goldens
import grader
import grading
import view
from faults import Missed

SHEET = {"left out": "not answered", "twice": "is answered twice", "stranger": "is not a question of this run",
         "not yes or no": "is not yes or no", "misquoted": "not found word for word", "no quote": "quotes nothing",
         "extra field": "nothing else"}
GOLDEN = ("all yes", "all no", "one wrong", "one-sided", "unanswered")
WORDS = ("maybe", "unknown", "Yes", "YES", " yes", "no.", "", "yes or no")  # answers that are text but not yes or no
VIEW = ("arm", "message", "log", "file")


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


def _asked(pages, rng):
    """One page the seed chooses among those with questions for graders."""
    asked = [page for page in pages if page[3]]
    if not asked:
        raise Missed("no golden of the chosen case has a question for graders")
    return rng.choice(asked)


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
    """A correct sheet of one golden's page, then planted sheets for each of its answers in turn, given as `yes` and as
    `no`, with every word of WORDS for `not yes or no` and empty or blank evidence for `no quote`, and for `extra
    field` the file itself holding another field too. Caught when the sheet check accepts the correct sheet and
    refuses every planted one for the reason the place names."""
    _, pages = _pages(setup, rng)
    golden, record, blob, asked = _asked(pages, rng)
    page, ids = _text(record, blob), [question["id"] for question in asked]
    clean = _sheet(page, asked, golden.settled.get)
    problems = grading.check(clean, ids, page)
    if problems:
        return f"the sheet check refused the clean sheet: {problems}"
    answers, quote = clean["answers"], f"hw-{rng.getrandbits(32):08x} says so"
    edits = {"not yes or no": [lambda one, word=word: {**one, "answer": word} for word in WORDS],
             "misquoted": [lambda one: {**one, "evidence": quote}],
             "no quote": [lambda one, empty=empty: {**one, "evidence": empty} for empty in ("", " ", "\n\t ")],
             "extra field": [lambda one: {**one, "confidence": "high"}]}
    planted = []
    for n, value in ((n, value) for n in range(len(answers)) for value in grading.ANSWERS):
        base = [*answers[:n], {**answers[n], "answer": value}, *answers[n + 1:]]  # a valid sheet, either answer
        one, before, after = base[n], base[:n], base[n + 1:]
        if place in edits:
            planted += [before + [edit(one)] + after for edit in edits[place]]
        else:
            planted.append({"left out": before + after, "twice": base + [one],
                            "stranger": base + [{**one, "id": f"q{len(ids) + 100}"}]}[place])
    files = [{"answers": answers_} for answers_ in planted]
    if place == "extra field":  # the file itself holding another field
        files.append({**clean, "notes": "planted"})
    for file in files:
        problems = grading.check(file, ids, page)
        if not any(SHEET[place] in problem for problem in problems):
            return f"the sheet check did not refuse it as {SHEET[place]!r}: {problems}"
    return None


def _gate(case, pages, answer, ungraded=None):
    """The golden gate on `pages` graded by a panel of two planted graders that both answer by `answer(golden, id)`,
    but for the golden named `ungraded`, whose panel has one grader with no sheet, so it answers nothing."""
    graded = {}
    for golden, record, blob, asked in pages:
        one = _grader(lambda id_, golden=golden: answer(golden, id_))
        pair = [_grader(None), one] if golden.name == ungraded else [one, one]
        found = grader.panel(_text(record, blob), asked, pair, _grader(None))
        graded[golden.name] = ([question["id"] for question in asked], found.answers)
    return goldens.gate(case, [p[0] for p in pages], graded)


def _ids(page):
    return [question["id"] for question in page[3]]


def _both(pages, id_):
    return {page[0].settled[id_] for page in pages if id_ in _ids(page)} == set(grading.ANSWERS)


def golden(setup, fault, rng, place):
    """Graders, or goldens, wrong as `place` says, in every way the place allows: `all yes` and `all no` once; `one
    wrong`, each question of each golden in turn, alone, answered against its settled answer; `one-sided`, each
    trusted question in turn with only the goldens that settle it `yes`, then only those that settle it `no`;
    `unanswered`, each golden in turn with no answer from its panel. Caught when, in every one, the gate, which
    trusts a set of questions when graders give every settled answer on every golden, stops trusting exactly those
    of them the plant made wrong."""
    case, pages = _pages(setup, rng)
    right = lambda g, id_: g.settled[id_]
    trusted = {id_ for id_, why in _gate(case, pages, right).items() if why is None}
    if not trusted:
        return "the gate trusts no question even when graders give every settled answer"
    plants = []  # (the goldens kept, the answer, the golden left unanswered, the questions the plant makes wrong)
    if place in ("all yes", "all no"):
        value = place.split()[1]
        plants.append((pages, lambda g, id_: value, None,
                       {id_ for p in pages for id_ in _ids(p) if id_ in trusted and p[0].settled[id_] != value}))
    for p in pages if place == "one wrong" else []:
        for id_ in sorted(trusted & set(_ids(p))):
            answer = lambda g, q, name=p[0].name, id_=id_: _flip(g.settled[q]) if (g.name, q) == (name, id_) \
                else g.settled[q]
            plants.append((pages, answer, None, {id_}))
    for target, side in ((t, a) for t in sorted(trusted) for a in grading.ANSWERS) if place == "one-sided" else ():
        kept = [p for p in pages if target not in _ids(p) or p[0].settled[target] == side]
        plants.append((kept, right, None, {id_ for id_ in trusted if not _both(kept, id_)}))
    for p in pages if place == "unanswered" else []:
        if trusted & set(_ids(p)):
            plants.append((pages, right, p[0].name, trusted & set(_ids(p))))
    if not plants:
        raise Missed(f"the chosen case gives the plant {place!r} nothing to make wrong")
    for kept, answer, ungraded, wrong in plants:
        found = _gate(case, kept, answer, ungraded)
        flagged = {id_ for id_ in trusted if found[id_] is not None}
        if not wrong or flagged != wrong:
            return f"the gate stopped trusting {sorted(flagged)}, not the {sorted(wrong)} the plant made wrong"
    return None


def tie(setup, fault, rng, place):
    """Two graders of one page that split as `place` says (`one split`: on each question in turn), and a fresh
    tie-breaker, in two panels for each split: the tie-breaker sides with the first grader on a split question in one
    and with the second in the other, and with one grader ungraded, each grader is the ungraded one once. Caught
    when, in every panel, the tie-breaker is asked exactly the split questions and the panel takes its answers, or,
    with one grader ungraded, no question is answered and none asked."""
    _, pages = _pages(setup, rng)
    golden, record, blob, asked = _asked(pages, rng)
    page, ids, settled = _text(record, blob), [question["id"] for question in asked], golden.settled
    splits = {"one split": [[id_] for id_ in ids], "all split": [ids], "one ungraded": [[]]}[place]
    for split, turn in ((split, turn) for split in splits for turn in (0, 1)):
        order = rng.sample(split, len(split))
        calls = []
        if place == "one ungraded":
            pair = [_grader(settled.get), _grader(None)]
            found = grader.panel(page, asked, pair[::-1] if turn else pair, _grader(settled.get, calls))
            if calls or found.answers or found.unanswered != ids:
                return f"one grader decided alone: tie-breaker asked {calls}, answers {found.answers}"
            continue
        second = lambda id_, split=split: _flip(settled[id_]) if id_ in split else settled[id_]
        sides = {id_: (n + turn) % 2 for n, id_ in enumerate(order)}  # 0: with the first grader, 1: the second
        deciding = lambda id_, sides=sides: settled[id_] if sides.get(id_, 0) == 0 else _flip(settled[id_])
        found = grader.panel(page, asked, [_grader(settled.get), _grader(second)], _grader(deciding, calls))
        want = {id_: deciding(id_) for id_ in ids}
        if calls != [[id_ for id_ in ids if id_ in split]] or found.answers != want or found.unanswered:
            return f"the tie-breaker was asked {calls}, not the split {split}, and the panel gave {found.answers}"
    return None


def view_(setup, fault, rng, place):
    """The arm, or the skill's name and each of its paths on lines of their own, put in one golden's record at
    `place`, everywhere that place can carry them: the final message; every kind of log entry (`host.ENTRIES`), as an
    action on each path or as lines in its text; a world file's text, a file on each path, a link to one, and their
    changes. Its control is the same record with the plant's actions on the overlay left out and its lines that name
    the skill left out. Caught when the clean view and page name none of them, and the planted view and page equal
    the control's: nothing of the plant shows, not even an entry with its names taken out."""
    _, pages = _pages(setup, rng)
    _, record, blob, _ = rng.choice(pages)
    layer = record["overlay"]
    skill, files = layer["skill"], [f"{path}/SKILL.md" for path in layer["paths"]]
    names = [skill, *layer["paths"], "with_skill", "without_skill"]
    lines = "".join(f"{line}\n" for line in (skill, *files))
    planted, control, added = copy.deepcopy(record), copy.deepcopy(record), {}
    if place == "arm":
        planted["arm"], control["arm"] = "with_skill", "without_skill"
    elif place == "message":
        planted["final_message"] = lines + (record["final_message"] or "")
        control["final_message"] = record["final_message"] or ""
    elif place == "log":
        acts = [{"kind": "skill", "name": skill}] + [entry for file in files for entry in (
            {"kind": "read", "path": file}, {"kind": "write", "path": file, "sha256": None},
            {"kind": "command", "command": f"cat {file}", "output": "", "exit_code": 0},
            {"kind": "blocked", "action": f"cat {file}", "reason": "refused"})]
        texts = [("agent", "task", {}), ("message", "text", {}), ("blocked", "reason", {"action": "ls"})]
        made = lambda text: [{"kind": kind, field: text, **other} for kind, field, other in texts]
        planted["log"][:0] = [{**entry, "source": "observed"} for entry in acts + made(f"{lines}do the work\n")]
        control["log"][:0] = [{**entry, "source": "observed"} for entry in made("do the work\n")]
    else:
        target, entry = next((p, e) for p, e in sorted(record["files_after"].items()) if e.startswith("file "))
        old, data = entry.split(" ")[1], lines.encode() + blob(entry.split(" ")[1])
        new = hashlib.sha256(data).hexdigest()
        added[new] = data
        planted["files_after"][target] = f"file {new}{entry[len('file ') + 64:]}"
        for item in planted["log"]:  # the agent wrote the planted bytes, so its write's hash is theirs
            if item["kind"] == "write" and item.get("sha256") == old:
                item["sha256"] = new
        link = f"{target}.hw-link"
        for one, target_ in ((planted, files[0]), (control, "")):
            one["files_after"][link] = f"link {target_}"
            one["diff"][link] = {"before": None, "after": f"link {target_}"}
        for file in files:
            planted["files_after"][file] = entry
            planted["diff"][file] = {"before": None, "after": entry}
    read = lambda digest: added[digest] if digest in added else blob(digest)
    if _shown(record, blob, names):
        return "the clean view already names the arm or the skill, so the plant proves nothing"
    shown = _shown(planted, read, names)
    if shown:
        return f"the view a grader gets names {shown}"
    if _seen(planted, read) != _seen(control, blob):
        return "the view a grader gets differs from its control's: the plant shows"
    return None


def _seen(record, blob):
    seen, blobs = view.view(record, blob)
    return seen, blobs, grading.page(seen, blobs)


def _shown(record, blob, names):
    """The names that the view of `record` (its record and every blob) or its page holds."""
    seen, blobs, page = _seen(record, blob)
    text = json.dumps(seen, ensure_ascii=False) + "".join(data.decode("utf-8", "replace") for data in blobs.values())
    return [name for name in names if name in text + page]


PLANTS = {
    "sheet": (sheet, tuple(SHEET), False),
    "golden": (golden, GOLDEN, False),
    "tie": (tie, ("one split", "all split", "one ungraded"), False),
    "view": (view_, VIEW, False),
}
