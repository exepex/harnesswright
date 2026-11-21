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
  sheet, whose host's fresh grader stands in and answers half the questions the other way. A fresh tie-breaker must
  be asked exactly the split questions, and its answer, which sides with each grader on some question, must decide
  them; when the stand-in gives no sheet either, no question is answered and no tie-breaker is asked, so one grader
  never decides alone (`grader.panel`).
- `view`: the arm, or the skill's name and each of its paths, on lines of their own, inside a sentence, in the
  lead line that pins the skill's load (`host.lead`), under the world's absolute path and in backticks, with the
  run's own folders and a command's output that names them, put in a record's arm and what its host reported
  (exposure, requests, failure), final message, every kind of log entry (with the inferred entries of a command),
  or files and changes (each overlay path as a run holds it, with its folders, the
  folders above it, its files and their writes; a link to one; lines in a world file's text, and its write). Neither the
  view (`view.view`, its record and every blob) nor the page (`grading.page`) may name any of them, and the clean ones
  name none, reading an arm word everywhere except in a world file both arms hold byte for byte (`tells`). The world
  file that holds the plant's lines names no arm word. And the planted view and page must equal those of a control,
  the same record without the plant's actions on
  the overlay and its lines that name the skill: a tell with its names taken out, such as an empty skill-load entry,
  still shows.

Standard library only.
"""

import copy
import hashlib
import re
import shutil
import string
from pathlib import PurePosixPath

import cases
import checks
import evidence
import goldens
import grader
import grading
import host
import scrub
import tells
import view
from faults import Missed

SHEET = {"left out": "not answered", "twice": "is answered twice", "stranger": "is not a question of this run",
         "not yes or no": "is not yes or no", "misquoted": "not found word for word", "no quote": "quotes nothing",
         "extra field": "nothing else"}
GOLDEN = ("all yes", "all no", "one wrong", "one-sided", "unanswered")
WORDS = ("maybe", "unknown", "Yes", "YES", " yes", "no.", "", "yes or no")  # answers that are text but not yes or no
VIEW = ("arm", "message", "log", "file")
SHOWN = view.FIELDS  # what the view is meant to show; every other field of a record a plant fills


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


def _text(case, record, blob):
    return grading.page(case.prompt, *view.view(record, blob))


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


def _once(answer, calls):
    """A planted grader of a host whose first grader gives no sheet and whose next grader answers by `answer`, as
    `_grader` does."""
    def grade_one(page, asked):
        return _grader(answer if calls else None, calls)(page, asked)
    return grade_one


def sheet(setup, fault, rng, place):
    """A correct sheet of one golden's page, then planted sheets for each of its answers in turn, given as `yes` and as
    `no`, with every word of WORDS for `not yes or no`, every misquote (invented, in other case, a word changed,
    the words reversed) for `misquoted` and empty or blank evidence for `no quote`, and for `extra
    field` the file itself holding another field too. Caught when the sheet check accepts the correct sheet and
    refuses every planted one for the reason the place names."""
    case, pages = _pages(setup, rng)
    golden, record, blob, asked = _asked(pages, rng)
    page, ids = _text(case, record, blob), [question["id"] for question in asked]
    clean = _sheet(page, asked, golden.settled.get)
    problems = grading.check(clean, ids, page)
    if problems:
        return f"the sheet check refused the clean sheet: {problems}"
    answers, line = clean["answers"], clean["answers"][0]["evidence"]
    words = line.split()
    misquotes = [quote for quote in (f"hw-{rng.getrandbits(32):08x} says so", line.swapcase(),
                                     " ".join(words[:-1] + ["hw-other"]), " ".join(reversed(words)))
                 if _words(quote) != _words(line)]  # invented, in other case, a word changed, reversed
    edits = {"not yes or no": [lambda one, word=word: {**one, "answer": word} for word in WORDS],
             "misquoted": [lambda one, quote=quote: {**one, "evidence": quote} for quote in misquotes],
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


def _words(text):
    """The words of a quote as doc 11 reads them, worked out here and not by the check under test."""
    return re.findall(r"[^\W_]+", text)


def _gate(case, pages, answer, ungraded=None):
    """The golden gate on `pages` graded by a panel of two planted graders that both answer by `answer(golden, id)`,
    but for the golden named `ungraded`, whose panel has one grader with no sheet, so it answers nothing."""
    graded = {}
    for golden, record, blob, asked in pages:
        one = _grader(lambda id_, golden=golden: answer(golden, id_))
        pair = [_grader(None), one] if golden.name == ungraded else [one, one]
        found = grader.panel(_text(case, record, blob), asked, pair, _grader(None))
        graded[golden.name] = ([question["id"] for question in asked], found.answers, found.flipped)
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
    """Two graders of one page that split as `place` says, and a fresh tie-breaker, by one rule for every place: on
    the split questions the tie-breaker sides with the first grader on some and with the second on the rest, each way
    in one of two panels. `one split` splits on each question in turn, `all split` on every question, and `one
    ungraded` on half the questions (at least one), where the second sheet comes from a fresh grader standing in for
    one that gave none, each grader being the ungraded one once for each side the tie-breaker takes. Caught when, in every panel, the tie-breaker is asked
    exactly the split questions and the panel takes its answers; with one grader ungraded, also when that host's
    grader is asked every question twice, and, when its stand-in gives no sheet either, nothing is answered and the
    tie-breaker is asked nothing: one grader never decides alone."""
    case, pages = _pages(setup, rng)
    golden, record, blob, asked = _asked(pages, rng)
    page, ids, settled = _text(case, record, blob), [question["id"] for question in asked], golden.settled
    splits = {"one split": [[id_] for id_ in ids], "all split": [ids],
              "one ungraded": [rng.sample(ids, max(1, len(ids) // 2))]}[place]
    orders = [rng.sample(split, len(split)) for split in splits]  # one order for both turns of a split
    swaps = (0, 1) if place == "one ungraded" else (0,)  # with one ungraded, each grader is the ungraded one once
    for (split, order), turn, swap in ((pair, turn, swap) for pair in zip(splits, orders) for turn in (0, 1)
                                       for swap in swaps):
        calls, again = [], []
        second = lambda id_, split=split: _flip(settled[id_]) if id_ in split else settled[id_]
        sides = {id_: (n + turn) % 2 for n, id_ in enumerate(order)}  # 0: with the first grader, 1: the second
        deciding = lambda id_, sides=sides: settled[id_] if sides.get(id_, 0) == 0 else _flip(settled[id_])
        pair = [_grader(settled.get), _once(second, again) if place == "one ungraded" else _grader(second)]
        found = grader.panel(page, asked, pair[::-1] if swap else pair, _grader(deciding, calls))
        want = {id_: deciding(id_) for id_ in ids}
        stood_in = place != "one ungraded" or again == [ids, ids]
        if calls != [[id_ for id_ in ids if id_ in split]] or found.answers != want or found.unanswered or not stood_in:
            return (f"one grader decided alone: the tie-breaker was asked {calls}, not the split {split}, the panel "
                    f"gave {found.answers}, and the ungraded host was asked {again}")
        if place == "one ungraded":  # its stand-in gives no sheet either
            calls, again = [], []
            pair = [_grader(settled.get), _once(None, again)]
            found = grader.panel(page, asked, pair[::-1] if swap else pair, _grader(deciding, calls))
            if calls or found.answers or again != [ids, ids]:
                return (f"one grader decided alone with no stand-in sheet: the tie-breaker was asked {calls}, the "
                        f"panel gave {found.answers}, and the ungraded host was asked {again}")
    return None


def view_(setup, fault, rng, place):
    """The arm, or the skill's name and each of its paths, on lines of their own, inside a sentence, under the world's
    absolute path and in backticks, with the run's own folders and a command's output that names them, put in one
    golden's record at `place`, everywhere that place can carry them: the arm and what the host reported; the final
    message; every kind of log entry (`host.ENTRIES`), as an action on each path, with an inferred entry after its
    command, or as lines in its text; each overlay path as a run holds it (its folders, the folders above it, its files,
    their writes and changes), a link to one, and a world file's text and its write. Its control is the same record with
    the plant's actions on the overlay left out, its lines that name the skill left out, its run folders as their
    neutral words and its command output empty. Caught when the clean view and page name none of them, by the one
    rule of `tells` (an arm word may be only in a world file both arms of the case are built holding byte for byte),
    and the planted view and page equal the control's: nothing of the plant shows, not even an entry with its names
    taken out. The world file that takes the plant's lines is one whose text names no arm word."""
    case, pages = _pages(setup, rng)
    _, record, blob, _ = rng.choice(pages)
    layer = record["overlay"]
    skill, files = layer["skill"], [f"{path}/SKILL.md" for path in layer["paths"]]
    names = [skill, *evidence.places(layer)]  # the skill's paths and the files a team install adds
    world = next((f for f, word in record["folders"].items() if word == scrub.NEUTRAL_FOLDERS["world"]), "/world")
    edges = [c for c in string.punctuation + " " if not re.fullmatch(r"[\w-]", c)]  # every character not of a name
    lines = "".join(f"{line}\n" for line in (skill, *files, f"I used {skill}, from {files[-1]}, here.",
                                             *(host.lead(setup.adapter, skill, file) for file in files),  # a pin
                                             *(f"cat {world}/{file}" for file in files),
                                             *(f"x{c}{name}{c}x" for name in (skill, *files) for c in edges)))
    kept = f"hw-kept-{rng.getrandbits(32):08x}\n"  # a neutral line next to the plant, which the view must keep
    folders = sorted(record["folders"])  # the run's own folders, bare and at every edge, and as the view words them
    ran = "".join(f"{f}\n" + "".join(f"x{c}{f}{c}x\n" for c in edges) for f in folders)
    neutral = "".join(f"{w}\n" + "".join(f"x{c}{w}{c}x\n" for c in edges) for w in map(record["folders"].get, folders))
    word = record["folders"].get(world, world)
    planted, control, added = copy.deepcopy(record), copy.deepcopy(record), {}
    held, arms = tells.shared(case, setup.adapter, setup.folder, record), (*cases.ARMS, cases.PREVIOUS)

    def stored(data):
        added[hashlib.sha256(data).hexdigest()] = data
        return hashlib.sha256(data).hexdigest()

    if place == "arm":
        for field in sorted(set(record) - set(SHOWN) - {"overlay", "folders", "own_files"}):  # all kept back
            planted[field], control[field] = f"with_skill\n{lines}", None
        planted["folders"][f"/tmp/{skill}-with_skill"] = control["folders"]["/tmp/hw-plain"] = "/run/other"
    elif place == "message":
        planted["final_message"] = lines + kept + ran + (record["final_message"] or "")
        control["final_message"] = kept + neutral + (record["final_message"] or "")
    elif place == "log":
        world_file = sorted(path for path, entry in record["files_after"].items() if entry.startswith("file "))[0]
        acts = [{"kind": "skill", "name": skill}] + [entry for file in files for entry in (
            {"kind": "read", "path": file}, {"kind": "write", "path": file, "sha256": None},
            {"kind": "command", "command": f"cat {file} {world_file}", "output": "", "exit_code": 0},
            {"kind": "read", "path": world_file, "source": "inferred"},  # part of the command before it
            {"kind": "command", "command": f"cat {world}/{file}", "output": "", "exit_code": 0},
            {"kind": "blocked", "action": f"cat {world}/{file}", "reason": "refused"},
            {"kind": "blocked", "action": f"cat {file}", "reason": "refused"})]
        texts = [("agent", "task", {}), ("message", "text", {}), ("blocked", "reason", {"action": "ls"})]
        made = lambda text: [{"kind": kind, field: text, **other} for kind, field, other in texts]
        shown = lambda output, code: {"kind": "command", "command": "ls", "output": output, "exit_code": code}
        acted = lambda f: [{"kind": "command", "command": f"ls {f}", "output": "", "exit_code": 0},
                           {"kind": "blocked", "action": f"write {f}/notes.md", "reason": "refused"}]
        planted["log"][:0] = [{"source": "observed", **entry} for entry in acts + made(lines + kept + ran) + [
            shown(lines + ran, 1)] + [e for f in folders for e in acted(f)]]
        control["log"][:0] = [{**entry, "source": "observed"} for entry in made(kept + neutral) + [shown("", 0)] + [
            e for f in folders for e in acted(record["folders"][f])]]
    else:
        target, entry = next((p, e) for p, e in sorted(record["files_after"].items()) if e.startswith("file ")
                             and not any(arm in blob(e.split(" ")[1]).decode("utf-8", "replace") for arm in arms))
        old, rest = entry.split(" ")[1], entry[len("file ") + 64:]
        for one, data in ((planted, lines + kept + ran), (control, kept + neutral)):  # the agent wrote it
            digest = stored(data.encode() + blob(old))
            one["files_after"][target] = f"file {digest}{rest}"
            for item in one["log"]:
                if item["kind"] == "write" and item.get("sha256") == old:
                    item["sha256"] = digest
            one["log"].append({"kind": "write", "source": "observed", "path": target, "sha256": digest})
        link = f"{target}.hw-link"
        for one, to, was in ((planted, files[0], files[-1]), (control, "", "")):
            one["files_after"][link] = f"link {to}"
            one["diff"][link] = {"before": f"link {was}", "after": f"link {to}"}
        for one, root in ((planted, world), (control, word)):  # a link to a world file by the world's own folder
            one["files_after"][f"{link}-world"] = f"link {root}/{target}"
        for path in evidence.places(layer):  # the overlay as a run holds it: its folders, those above, its files
            above = [str(folder) for folder in PurePosixPath(path).parents if str(folder) != "."]
            own = stored(f"# {skill}\n{lines}".encode())  # the skill's own bytes, which the view must not hold
            made = {folder: "dir" for folder in above if folder not in record["files_after"]}
            file = f"{path}/SKILL.md" if path in layer["paths"] else path  # a skill's folder, or a file of a release
            made[file] = f"file {own}{rest}"
            if file != path:
                made.update({path: "dir", f"{path}/references": "dir", f"{path}/references/notes.md": made[file]})
            planted["files_after"].update(made)
            planted["diff"].update({name: {"before": None, "after": value} for name, value in made.items()})
            planted["log"].append({"kind": "write", "source": "observed", "path": file, "sha256": own})
    read = lambda digest: added[digest] if digest in added else blob(digest)
    for one, of in ((record, blob), (planted, read)):  # the clean record, then the planted one, by the same rule
        shown = tells.shown(case, one, of, names, held)
        if shown:
            return f"the view a grader gets names {shown}" + (" in the clean record" if one is record else "")
    seen = tells.seen(case, control, read)
    if place != "arm" and kept.strip() not in seen[2]:
        return "the control's page lost the neutral line next to the plant, so the view hides what it must show"
    if tells.seen(case, planted, read) != seen:
        return "the view a grader gets differs from its control's: the plant shows"
    return None


PLANTS = {
    "sheet": (sheet, tuple(SHEET), False),
    "golden": (golden, GOLDEN, False),
    "tie": (tie, ("one split", "all split", "one ungraded"), False),
    "view": (view_, VIEW, False),
}
