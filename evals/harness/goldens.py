"""Goldens (doc 11, Graders): hand-made runs of a case with settled answers, and the golden gate.

One rule: a golden becomes a bundle the way every run does, and an expectation's grading is trusted in a round only
when every golden got its settled answer, with at least one settled `yes` and one settled `no` among the goldens
it was asked of.

A golden is `evals/goldens/<skill>/<case>/<name>.json`, written by hand by a judge, never by the builder:

- `changes`: what the run did to the case's world, `{path: the file's new text, or null when the run removed the
  file}`. A path that is not a file of the world, or that runs through one, is refused when the golden is built.
- `log`: the run's actions, each an entry of `host.ENTRIES`, as a bundle's log holds them. Its last message, if it
  has one, is the final message, as in a run.
- `settled`: one answer for each expectation of the case, by its question id (`q1` is the first expectation):
  `{"expectation": its text, "sha256": its fingerprint (`fingerprint`), "answer": "yes" or "no", "by": the judge
  who settled it}`. The fingerprint covers the whole expectation, its text, check and judged question, rules and
  examples, so a golden never settles an expectation that has moved or changed in any way.

- `load(case, folder)`: the case's goldens, checked against that shape.
- `bundle(golden, case, adapter, out, drift, host_version, model)`: the golden as a run's record and blobs. The
  case's without-skill world is built for `adapter`'s host, the golden's changes are written into it, its log is
  kept as a host's is (`host.kept`), and `evidence.collect` reads it as it reads every run, with the
  case's real overlay (`evidence.overlay`). From there a golden goes the way of every run: the checks, the view, the
  page, the blind order and the panel, so nothing tells a grader or a check it is a golden. Its arm is `golden`,
  which no view shows.
- `gate(case, goldens, graded)`: for each question id of the case, None when its grading is trusted, or why not.
  Every golden must be in `graded`: one that was not graded cannot be left out of the gate.

Standard library only.
"""

import hashlib
import json
import os
from pathlib import Path

import cases
import contain
import evidence
import grading
import host
import manifest
import world

ROOT = cases.REPO / "evals" / "goldens"
FIELDS = ("changes", "log", "settled")
SETTLED_FIELDS = ("expectation", "sha256", "answer", "by")
NOTHING_EXPOSED = {"skills": [], "tools": []}


class GoldenError(ValueError):
    pass


class Golden:
    """One golden: its `name`, `changes`, `log`, and `settled`, {question id: "yes" or "no"}."""

    def __init__(self, name, data):
        self.name, self.changes, self.log = name, data["changes"], data["log"]
        self.settled = {id_: given["answer"] for id_, given in data["settled"].items()}


def fingerprint(expectation):
    """The sha256 of an expectation as the case holds it, every field included."""
    return hashlib.sha256(json.dumps(expectation, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load(case, folder=None):
    """The goldens of `case` (`cases.Case`), from `folder` (by default its folder under ROOT), sorted by name. A
    case with no folder has no goldens."""
    folder = Path(folder) if folder else ROOT / case.skill / case.id
    if not folder.is_dir():
        return []
    return [Golden(path.stem, check(path, case)) for path in sorted(folder.iterdir())]


def check(path, case):
    """The data of the golden at `path`, or GoldenError naming every way it is not a golden of `case`."""
    if path.suffix != ".json" or path.is_symlink() or not path.is_file() or not cases.is_name(path.stem):
        raise GoldenError(f"{path.name}: a golden is a file <name>.json, with a lower-case name")
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
        json.dumps(data, ensure_ascii=False).encode()  # a lone surrogate is no text a run could hold
    except (UnicodeError, json.JSONDecodeError) as error:
        raise GoldenError(f"{path.name}: not UTF-8 JSON: {error}") from None
    if not isinstance(data, dict) or set(data) != set(FIELDS):
        raise GoldenError(f"{path.name}: a golden holds {', '.join(FIELDS)} and nothing else")
    problems = []
    if not isinstance(data["changes"], dict) or not all(
            cases.is_path(p) and (t is None or isinstance(t, str)) for p, t in data["changes"].items()):
        problems.append("changes: {path: text or null}, each path relative and inside the world")
    try:
        host.check_log(data["log"])
    except host.HostError as error:
        problems.append(str(error))
    problems += _settled(data["settled"], case.expectations or [])
    if problems:
        raise GoldenError(f"{path.name}: " + "; ".join(problems))
    return data


def _settled(settled, expectations):
    expected = {f"q{number}": item for number, item in enumerate(expectations, start=1)}
    if not isinstance(settled, dict) or set(settled) != set(expected):
        return [f"settled: one answer for each expectation, {', '.join(expected)}, and no other"]
    problems = []
    for id_, given in settled.items():
        if not isinstance(given, dict) or set(given) != set(SETTLED_FIELDS):
            problems.append(f"settled {id_}: holds {', '.join(SETTLED_FIELDS)} and nothing else")
        elif (given["expectation"], given["sha256"]) != (expected[id_]["text"], fingerprint(expected[id_])):
            problems.append(f"settled {id_}: not the case's expectation as it is now: {expected[id_]['text']!r}, "
                            f"{fingerprint(expected[id_])}")
        elif given["answer"] not in grading.ANSWERS or not cases.is_name(given["by"]):
            problems.append(f"settled {id_}: the answer is yes or no, and by names the judge")
    return problems


def bundle(golden, case, adapter, out, drift, host_version, model, skills_root=None):
    """(record, blobs) of `golden` as a run of `case` on `adapter`'s host, made in the empty folder `out`, which the
    caller removes. `drift`, `host_version` and `model` are the round's, as for its runs (`evidence.collect`)."""
    out = Path(out)
    built = world.build(case, adapter, out / "world", skills_root)
    (out / "operator").mkdir()  # no sign-in: nothing runs
    contained = contain.Containment(adapter, case.kind, built.path, manifest.manifest(built.path), out / "run",
                                    operator_env={}, operator_home=out / "operator")
    wrong = [path for path, text in golden.changes.items() if not _write(built.path, path, text)]
    if wrong:
        raise GoldenError(f"{golden.name}: not a file of the world, or under one: {', '.join(wrong)}")
    log = host.kept(contained, golden.log)  # as a host's reported log is kept, with the reads its commands name
    try:
        host.check_log(log, [install.name for install in built.installs])  # the skills this arm installs, as a run's
    except host.HostError as error:
        raise GoldenError(f"{golden.name}: {error}") from None
    result = host.Result("", "", 0, False, None, log, NOTHING_EXPOSED, [], 0.0)
    layer = evidence.overlay(case, adapter, skills_root)
    return evidence.collect(contained, result, case, "golden", layer, drift, host_version, model)


def _write(root, path, text):
    """Make the world at `root` hold `text` at `path`, or no file there when `text` is None, as a run's write or
    removal does. False when that is not what a run could do: removing what is not a file, or writing through a
    file or onto a folder or link. A file written again keeps its mode, as it does in a run."""
    target = root / path
    parents = [root / Path(path).parents[n] for n in range(len(Path(path).parts) - 1)]
    if any(p.is_symlink() or (p.exists() and not p.is_dir()) for p in parents) or os.path.islink(target):
        return False
    if text is None:
        if not target.is_file():
            return False
        target.unlink()
        return True
    if target.exists() and not target.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    return True


def gate(case, goldens, graded):
    """{question id: None, or why its grading is not trusted this round} for every expectation of `case`.
    `goldens` are its goldens (`load`); `graded` is {golden name: (the ids it was asked, the answers its panel gave)},
    one entry for every golden. A question left unanswered is a miss."""
    if set(graded) != {golden.name for golden in goldens}:
        raise GoldenError("the gate needs the grading of every golden, and of no other run")
    found = {}
    for id_ in (f"q{number}" for number in range(1, len(case.expectations or []) + 1)):
        asked = [golden for golden in goldens if id_ in graded[golden.name][0]]
        missed = [f"{golden.name} got {graded[golden.name][1].get(id_, 'no answer')}, not {golden.settled[id_]}"
                  for golden in asked if graded[golden.name][1].get(id_) != golden.settled[id_]]
        if missed:
            found[id_] = "a golden was missed: " + "; ".join(missed)
        elif {golden.settled[id_] for golden in asked} != set(grading.ANSWERS):
            found[id_] = "no golden with a settled yes and one with a settled no was asked it"
        else:
            found[id_] = None
    return found
