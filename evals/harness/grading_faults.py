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
- `view`: what the harness adds (`view.ADDED`) put in a record beside the run's own words that name the skill and
  its paths: the arm and what its host reported (exposure, requests, failure); the lead line that pins the skill's
  load (`host.lead`) and the run's real folders, in the final message, in every kind of log entry and in a world
  file's text and a link; the load the lead line pins and a command's output and exit code, in the log; and each
  overlay path as a run holds it (its folders, the folders above it, its files and their writes) and the line the
  install adds to a file it edits in place (the index row, a team profile's version line), in the files. Neither
  the view (`view.view`, its record and every blob) nor the page (`grading.page`) may show any of it, and the clean
  ones show none, reading an arm word everywhere except in a world file both arms hold byte for byte (`tells`). The
  planted view and page must equal those of a control, the same record with the run's own words only, and the
  control's page must still show those words: a view that hides what the run wrote is a miss too.

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
import manifest
import scrub
import teamrelease
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
RULES_FILES = (".harness/runs/{run}/rules.md", ".harness/runs/{run}/rules-text-{skill}.{stack}.md")  # a run writes


def _flip(answer):
    return "no" if answer == "yes" else "yes"


def _pages(setup, rng):
    """(case, [(golden, record, blob, asked)]) for the goldens of the repository case the seed chooses."""
    found = held()
    if not found:
        raise Missed("the repository has no goldens to plant grading faults on")
    return built(setup, *rng.choice(found))


def held():
    """Each repository case with goldens, as (skill, case id), in order."""
    return [(s.name, c.name) for s in sorted(goldens.ROOT.glob("*")) if s.is_dir() for c in sorted(s.iterdir())]


def built(setup, skill, name):
    """(case, [(golden, record, blob, asked)]) for the goldens of the case `name` of `skill`."""
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


def view_(setup, fault, rng, place):
    """What the harness adds, put in one golden's record at `place` beside the run's own words, as the module says.
    The run's own words are the skill's name and each installed path, on lines of their own, inside a sentence,
    under the world's absolute path and in backticks, and as actions on each path (a command, a read of a file in
    the skill's folder, a write, a refused action, a link, a file under a longer name of the skill, a run's rules
    files); the planted record holds them too, and its control holds them alone, with its folders as their neutral
    words and its command output empty. Caught when the clean view and page show nothing the harness added
    (`tells.shown`), the planted view and page equal the control's, and the control's page shows the run's words."""
    case, pages = _pages(setup, rng)
    _, record, blob, _ = rng.choice(pages)
    held, arms = tells.shared(tells.built(case, setup.adapter, setup.folder), record), (*cases.ARMS, cases.PREVIOUS)
    shows = tells.seen(case, record, blob)[0]["files_after"]  # a world file a plant acts on is one the view shows
    layer = record["overlay"]
    skill, files = layer["skill"], [f"{path}/SKILL.md" for path in layer["paths"]]
    world = next((f for f, word in record["folders"].items() if word == scrub.NEUTRAL_FOLDERS["world"]), "/world")
    word = record["folders"].get(world, world)
    edges = [c for c in string.punctuation + " " if not re.fullmatch(r"[A-Za-z0-9]", c)]  # each not of a name
    mine = lambda root: "".join(f"{line}\n" for line in (  # the run's own words, with the world at `root`
        skill, *files, f"I used {skill}, from {files[-1]}, here.", *(f"cat {root}/{file}" for file in files),
        *(f"x{c}{name}{c}x" for name in (skill, *files) for c in edges)))
    leads = [host.lead(setup.adapter, skill, file) for file in files]
    pins = "".join(f"{lead}\n" for lead in leads)
    kept = f"hw-kept-{rng.getrandbits(32):08x}\n"  # a neutral line next to the plant, which the view must keep
    folders = sorted(record["folders"])  # the run's own folders, bare and at every edge, and as the view words them
    ran = "".join(f"{f}\n" + "".join(f"x{c}{f}{c}x\n" for c in edges) for f in folders)
    neutral = "".join(f"{w}\n" + "".join(f"x{c}{w}{c}x\n" for c in edges) for w in map(record["folders"].get, folders))
    planted, control, added = copy.deepcopy(record), copy.deepcopy(record), {}
    harness, own = pins + mine(world) + kept + ran, mine(word) + kept + neutral  # a planted text and its control's

    def stored(data):
        added[hashlib.sha256(data).hexdigest()] = data
        return hashlib.sha256(data).hexdigest()

    if place == "arm":
        for field in sorted(set(record) - set(SHOWN) - {"overlay", "folders", "own_files"}):  # all kept back
            planted[field], control[field] = f"with_skill\n{pins}{mine(world)}", None
        planted["folders"][f"/tmp/{skill}-with_skill"] = control["folders"]["/tmp/hw-plain"] = "/run/other"
    elif place == "message":
        planted["final_message"] = harness + (record["final_message"] or "")
        control["final_message"] = own + (record["final_message"] or "")
    elif place == "log":
        world_file = sorted(path for path, entry in record["files_after"].items() if entry.startswith("file ")
                            and path in shows)[0]
        acts = lambda root: [entry for file in files for entry in (  # the run's own actions on each path
            {"kind": "read", "path": f"{file.rsplit('/', 1)[0]}/references/notes.md"},
            {"kind": "write", "path": file, "sha256": None},
            {"kind": "command", "command": f"cat {file} {world_file}", "output": "", "exit_code": 0},
            {"kind": "read", "path": world_file, "source": "inferred"},  # part of the command before it
            {"kind": "command", "command": f"cat {root}/{file}", "output": "", "exit_code": 0},
            {"kind": "blocked", "action": f"cat {root}/{file}", "reason": "refused"})]
        pin = [{"kind": "skill", "name": skill}] + [entry for file in files for entry in (  # the load it pins
            {"kind": "read", "path": file}, {"kind": "read", "path": f"{world}/{file}", "source": "inferred"})]
        texts = [("agent", "task", {}), ("message", "text", {}), ("blocked", "reason", {"action": "ls"})]
        made = lambda text: [{"kind": kind, field: text, **other} for kind, field, other in texts]
        shown = lambda output, code: {"kind": "command", "command": "ls", "output": output, "exit_code": code}
        acted = lambda f: [{"kind": "command", "command": f"ls {f}", "output": "", "exit_code": 0},
                           {"kind": "blocked", "action": f"write {f}/notes.md", "reason": "refused"}]
        planted["log"][:0] = [{"source": "observed", **entry} for entry in pin + acts(world) + made(harness) + [
            shown(pins + mine(world) + ran, 1)] + [e for f in folders for e in acted(f)]]
        control["log"][:0] = [{"source": "observed", **entry} for entry in acts(word) + made(own) + [
            shown("", 0)] + [e for f in folders for e in acted(record["folders"][f])]]
    else:
        target, entry = next((p, e) for p, e in sorted(record["files_after"].items()) if e.startswith("file ")
                             and p in shows and not any(
                                 arm in blob(e.split(" ")[1]).decode("utf-8", "replace") for arm in arms))
        old, rest = entry.split(" ")[1], entry[len("file ") + 64:]
        for one, data in ((planted, harness), (control, own)):  # the agent wrote it
            digest = stored(data.encode() + blob(old))
            one["files_after"][target] = f"file {digest}{rest}"
            for item in one["log"]:
                if item["kind"] == "write" and item.get("sha256") == old:
                    item["sha256"] = digest
            one["log"].append({"kind": "write", "source": "observed", "path": target, "sha256": digest})
        rules = [name.format(run="hw-run", skill=skill, stack="core") for name in RULES_FILES]
        for one, root in ((planted, world), (control, word)):  # the run's links, a longer name and rules files
            one["files_after"][f"{target}.hw-link"] = f"link {files[0]}"
            one["files_after"][f"{target}.hw-link-world"] = f"link {root}/{target}"
            above = {str(f) for file in rules for f in PurePosixPath(file).parents if str(f) != "."}
            made = {folder: "dir" for folder in sorted(above) if folder not in record["files_after"]}
            made.update({file: f"file {stored(f'| CORE-WORK-01 | {skill} |'.encode())}{rest}"
                         for file in [*rules, f"notes-{skill}.md"]})
            one["files_after"].update(made)
            one["diff"].update({name: {"before": None, "after": value} for name, value in made.items()})
        # Each line the install adds to a file it edits in place, the index row and a team profile's version line,
        # goes in that file as the planted record holds it, so in what each of the run's writes of it wrote.
        index = layer.get("index")
        named = [p for p in layer.get("release", []) if PurePosixPath(p).name == teamrelease.SELF]
        lines = {path: f'  version: "0.0.0"  # checked against {named[0]}\n'
                 for path in set(layer.get("edited") or {}) - {index} if named}
        if index and layer.get("row"):
            lines[index] = layer["row"] + "\n"
        for path, line in sorted(lines.items()):
            was = planted["files_after"].get(path, "")
            if manifest.is_file(was):
                data = added.get(was.split(" ")[1]) or blob(was.split(" ")[1])
                planted["files_after"][path] = f"file {stored(data + line.encode())}{was[len('file ') + 64:]}"
                for item in planted["log"]:
                    if item["kind"] == "write" and item.get("sha256") == was.split(" ")[1]:
                        item["sha256"] = planted["files_after"][path].split(" ")[1]
        for path in evidence.places(layer):  # the overlay as a run holds it: its folders, those above, its files
            above = [str(folder) for folder in PurePosixPath(path).parents if str(folder) != "."]
            mark = stored(f"# {skill}\nhw-skill-{rng.getrandbits(32):08x}\n".encode())  # the skill's own bytes
            made = {folder: "dir" for folder in above if folder not in record["files_after"]}
            file = f"{path}/SKILL.md" if path in layer["paths"] else path  # a skill's folder, or a file of a release
            made[file] = f"file {mark}{rest}"
            if file != path:
                made.update({path: "dir", f"{path}/references": "dir", f"{path}/references/notes.md": made[file]})
            planted["files_after"].update(made)
            planted["diff"].update({name: {"before": None, "after": value} for name, value in made.items()})
    read = lambda digest: added[digest] if digest in added else blob(digest)
    words = [*leads, *folders]  # what only the harness writes
    for one, of in ((record, blob), (planted, read)):  # the clean record, then the planted one, by the same rule
        shown = tells.shown(case, one, of, words, held)
        if shown:
            return f"the view a grader gets names {shown}" + (" in the clean record" if one is record else "")
    seen = tells.seen(case, control, read)
    if place != "arm" and not all(line in seen[2] for line in (kept.strip(), *mine(word).splitlines())):
        return "the control's page lost the run's own words, so the view hides what it must show"
    if tells.seen(case, planted, read) != seen:
        return "the view a grader gets differs from its control's: the plant shows"
    return None


PLANTS = {
    "sheet": (sheet, tuple(SHEET), False),
    "golden": (golden, GOLDEN, False),
    "view": (view_, VIEW, False),
}
