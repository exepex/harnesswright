"""Goldens (doc 11, Graders): hand-made runs of a case with settled answers, and the golden gate.

One rule: a golden is graded exactly as a run is, and an expectation's grading is trusted in a round only when the
goldens it was asked of all got their settled answer, and hold at least one settled `yes` and one settled `no`.

A golden is `evals/goldens/<skill>/<case>/<name>.json`, written by hand by a judge, never by the builder:

- `changes`: what the run changed in the case's world, `{path: text, or null when the run removed the file}`.
- `log`: the run's actions, each an entry of `host.ENTRIES`, as a bundle's log holds them. Its last message, if it
  has one, is the final message, as in a run.
- `settled`: one answer for each expectation of the case, by its question id (`q1` is the first expectation):
  `{"expectation": its text, "answer": "yes" or "no", "by": the judge who settled it}`. The text must be the
  expectation's own, so a golden never settles an expectation that has moved or changed.

- `load(case, folder)`: the case's goldens, checked against that shape.
- `bundle(golden, case, adapter, out)`: the golden as a run's bundle (record and blobs): the case's without-skill
  world built for `adapter`'s host (`world.build`) in the empty folder `out`, with the golden's changes and log on
  top. From there a golden goes the way of every run: `checks.Bundle` for the checks, `view.view` and
  `grading.page` for the graders, mixed in by `grader.blind`, so nothing tells a grader it is a golden.
- `gate(case, goldens, graded)`: for each question id of the case, None when its grading is trusted, or why not.

Standard library only.
"""

import hashlib
import json
from pathlib import Path

import cases
import evidence
import grading
import host
import manifest
import world

ROOT = cases.REPO / "evals" / "goldens"
FIELDS = ("changes", "log", "settled")
SETTLED_FIELDS = ("expectation", "answer", "by")


class GoldenError(ValueError):
    pass


class Golden:
    """One golden: its `name`, `changes`, `log`, and `settled`, {question id: "yes" or "no"}."""

    def __init__(self, name, data):
        self.name, self.changes, self.log = name, data["changes"], data["log"]
        self.settled = {id_: given["answer"] for id_, given in data["settled"].items()}


def load(case, folder=None):
    """The goldens of `case` (`cases.Case`), from `folder` (by default its folder under ROOT), sorted by name. A
    case with no folder has no goldens."""
    folder = Path(folder) if folder else ROOT / case.skill / case.id
    if not folder.is_dir():
        return []
    return [Golden(path.stem, check(path, case)) for path in sorted(folder.iterdir())]


def check(path, case):
    """The data of the golden at `path`, or GoldenError naming every way it is not a golden of `case`."""
    if path.suffix != ".json" or not path.is_file() or path.is_symlink() or not cases.is_name(path.stem):
        raise GoldenError(f"{path.name}: a golden is a file <name>.json, with a lower-case name")
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GoldenError(f"{path.name}: not UTF-8 JSON: {error}") from None
    if not isinstance(data, dict) or set(data) != set(FIELDS):
        raise GoldenError(f"{path.name}: a golden holds {', '.join(FIELDS)} and nothing else")
    problems = []
    changes = data["changes"]
    if not isinstance(changes, dict) or not all(cases.is_path(p) and (t is None or isinstance(t, str))
                                                for p, t in changes.items()):
        problems.append("changes: {path: text or null}, each path relative and inside the world")
    try:
        host.check_log(data["log"])
    except host.HostError as error:
        problems.append(str(error))
    expected = {f"q{number}": item["text"] for number, item in enumerate(case.expectations or [], start=1)}
    settled = data["settled"]
    if not isinstance(settled, dict) or set(settled) != set(expected):
        problems.append(f"settled: one answer for each expectation, {', '.join(expected)}, and no other")
    else:
        for id_, given in settled.items():
            if not isinstance(given, dict) or set(given) != set(SETTLED_FIELDS):
                problems.append(f"settled {id_}: holds {', '.join(SETTLED_FIELDS)} and nothing else")
            elif given["expectation"] != expected[id_]:
                problems.append(f"settled {id_}: the expectation is not the case's own: {expected[id_]!r}")
            elif given["answer"] not in grading.ANSWERS or not cases.is_name(given["by"]):
                problems.append(f"settled {id_}: the answer is yes or no, and by names the judge")
    if problems:
        raise GoldenError(f"{path.name}: " + "; ".join(problems))
    return data


def bundle(golden, case, adapter, out, skills_root=None):
    """(record, blobs) of `golden` as a run of `case` in the without-skill world `world.build` makes for `adapter`'s
    host in the empty folder `out`, which the caller removes."""
    built = world.build(case, adapter, out, skills_root)
    before = manifest.manifest(built.path, skip=evidence.SKIP)
    blobs = {entry.split(" ")[1]: (built.path / path).read_bytes()
             for path, entry in before.items() if manifest.is_file(entry)}
    after = dict(before)
    for path, text in golden.changes.items():
        if text is None:
            after.pop(path, None)
            continue
        parts = path.split("/")
        after.update({"/".join(parts[:end]): "dir" for end in range(1, len(parts))})
        data = text.encode()
        blobs[hashlib.sha256(data).hexdigest()] = data
        after[path] = f"file {hashlib.sha256(data).hexdigest()}"
    messages = [item["text"] for item in golden.log if item["kind"] == "message"]
    record = {"case": case.id, "mode": case.kind, "files_after": after, "diff": evidence.diff(before, after),
              "log": golden.log, "final_message": messages[-1] if messages else None, "own_files": [], "folders": {},
              "overlay": {"skill": case.skill, "paths": [], "index": None, "index_without": None}}
    named = {entry.split(" ")[1] for entry in after.values() if manifest.is_file(entry)}
    return record, {digest: blobs[digest] for digest in named}


def gate(case, goldens, graded):
    """{question id: None, or why its grading is not trusted this round} for every expectation of `case`.
    `goldens` are its goldens (`load`); `graded` is {golden name: (the ids it was asked, the answers its panel gave)}
    for each golden graded in the round. A question left unanswered is a miss."""
    found = {}
    for id_ in (f"q{number}" for number in range(1, len(case.expectations or []) + 1)):
        asked = [golden for golden in goldens if id_ in graded.get(golden.name, ((), {}))[0]]
        missed = [f"{golden.name} got {graded[golden.name][1].get(id_, 'no answer')}, not {golden.settled[id_]}"
                  for golden in asked if graded[golden.name][1].get(id_) != golden.settled[id_]]
        if missed:
            found[id_] = "a golden was missed: " + "; ".join(missed)
        elif {golden.settled[id_] for golden in asked} != set(grading.ANSWERS):
            found[id_] = "no golden with a settled yes and one with a settled no was asked it"
        else:
            found[id_] = None
    return found
