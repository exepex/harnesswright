"""Grading (doc 11, Graders): which expectations of a run go to the graders, the page a grader reads, and the check
of a grading file.

One rule: a grader answers only what no check decided, from the grader view only, and every answer is checked
against that view.

- `questions(expectations, verdicts)`: the judged questions of one run. An expectation goes to the graders when it
  has no check, or its check gave `undecidable` on the run's bundle. Nothing else is sent, so a grader never
  overrules a script check. Each question keeps its expectation's place as its id (`q1` is the first expectation).
- `page(view, blobs)`: the one text a grader reads of a run, written from the grader view (`view.view`) and
  nothing else: the final message, the actions (each field's text as the agent wrote it, never escaped), the
  changes and the files. It is also the text every quote is checked against, so a grader is held to exactly what
  it was shown.
- `check(grading, ids, page)`: the problems of one grading file, none when it is accepted. A file is accepted
  only when it holds `answers` and nothing else, each answer is `{"id", "answer", "evidence"}` and nothing else,
  every id is answered exactly once and no other id is answered, each answer is `yes` or `no`, and each evidence
  is a quote found word for word in the page, with runs of white space read as one space.

Standard library only.
"""

import json
import re
from pathlib import Path

import manifest

KEYS = Path(__file__).resolve().parents[1] / "grading" / "keys"
ANSWERS = ("yes", "no")
ANSWER_FIELDS = ("id", "answer", "evidence")
JUDGED_FIELDS = ("question", "pass", "fail", "examples")
SPACE = re.compile(r"\s+")
UNSHOWN = ("kind", "source", "sha256")


class GradingError(RuntimeError):
    pass


def questions(expectations, verdicts):
    """[{"id", "question", "pass", "fail", "examples"}] for the expectations no check decided. `verdicts` holds one
    entry per expectation, in order: None for an expectation with no check, or what `checks.decide` gave for its
    check."""
    if len(verdicts) != len(expectations):
        raise GradingError(f"{len(verdicts)} verdicts for {len(expectations)} expectations")
    found = []
    for number, (expectation, verdict) in enumerate(zip(expectations, verdicts), start=1):
        if ("check" in expectation) != (verdict is not None):
            raise GradingError(f"expectation {number}: a verdict is given exactly when it has a check")
        if verdict is not None and verdict["check"] != expectation["check"]["name"]:
            raise GradingError(f"expectation {number}: the verdict is of {verdict['check']}, not of its check")
        if verdict is None or verdict["outcome"] == "undecidable":
            judged = expectation["judged"]
            found.append({"id": f"q{number}", **{name: judged[name] for name in JUDGED_FIELDS}})
    return found


def page(view, blobs):
    """The text a grader reads of one run's grader view (`view.view` gives `view` and `blobs`)."""
    final = view["final_message"]
    lines = ["# Final message", "", final if final is not None else "(none)", "", "# Actions", ""]
    for item in view["log"]:
        lines.append(f"- {item['kind']} ({item['source']})")
        lines += [f"  - {name}: {_value(value)}" for name, value in item.items() if name not in UNSHOWN]
    lines += ["", "# Changes", ""]
    for path, change in sorted(view["diff"].items()):
        state = "added" if not change["before"] else "removed" if not change["after"] else "changed"
        lines.append(f"- {path}: {state}")
    lines += ["", "# Files", ""]
    for path, entry in sorted(view["files_after"].items()):
        lines += [f"## {path}", "", _shown(entry, blobs), ""]
    return "\n".join(lines)


def _value(value):
    """A field's text as the agent wrote it, so a quote of a command as run is found on the page."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _shown(entry, blobs):
    if manifest.is_file(entry):
        data = blobs[entry.split(" ")[1]]
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return f"(not text, {len(data)} bytes)"
    if manifest.kind(entry) == "link":
        return "(a link to " + entry[len("link "):] + ")"
    return "(a folder)"


def check(grading, ids, page_text):
    """The problems of `grading` (a parsed grading file) for the question `ids` and the `page_text` the grader
    read, as a list of texts. An empty list means the file is accepted."""
    if not isinstance(grading, dict) or set(grading) != {"answers"} or not isinstance(grading["answers"], list):
        return ['a grading file holds "answers", a list, and nothing else']
    problems, seen = [], []
    shown = _flat(page_text)
    for number, answer in enumerate(grading["answers"], start=1):
        if not isinstance(answer, dict) or set(answer) != set(ANSWER_FIELDS) \
                or not all(isinstance(answer[name], str) for name in ANSWER_FIELDS):
            problems.append(f"answer {number}: holds {', '.join(ANSWER_FIELDS)} as texts, and nothing else")
            continue
        if answer["id"] not in ids:
            problems.append(f"answer {number}: {answer['id']!r} is not a question of this run")
        elif answer["id"] in seen:
            problems.append(f"answer {number}: {answer['id']} is answered twice")
        seen.append(answer["id"])
        if answer["answer"] not in ANSWERS:
            problems.append(f"answer {number}: {answer['answer']!r} is not yes or no")
        quote = _flat(answer["evidence"])
        if not quote:
            problems.append(f"answer {number}: the evidence quotes nothing")
        elif quote not in shown:
            problems.append(f"answer {number}: the evidence is not found word for word in the page")
    missing = [question for question in ids if question not in seen]
    if missing:
        problems.append(f"not answered: {', '.join(missing)}")
    return problems


def _flat(value):
    return SPACE.sub(" ", value).strip()


def keys(folder=KEYS):
    """The answer keys of `check`: ({key name: {"ids", "grading", "outcome", "problem"}}, the page they share), from
    `folder/*.json` and `folder/page.md`. A key's outcome is `pass` when the file must be accepted, and `fail` when
    it must not, with `problem`, a part of the problem it must be refused for."""
    found = {}
    for path in sorted(Path(folder).glob("*.json")):
        data = json.loads(path.read_text())
        fields = {"pass": {"ids", "grading", "outcome"}, "fail": {"ids", "grading", "outcome", "problem"}}
        if not isinstance(data, dict) or set(data) != fields.get(data.get("outcome"), set()):
            raise GradingError(f"{path}: an answer key holds ids, grading and outcome (pass, or fail with problem)")
        found[path.stem] = data
    return found, (Path(folder) / "page.md").read_text()


def prove(folder=KEYS):
    """The answer keys `check` gets wrong, as {key: its problems}: a key that must pass and has a problem, or one
    that must fail and has none that names its `problem`. GradingError unless there is a key of each outcome."""
    given, shared = keys(folder)
    if not {"pass", "fail"} <= {data["outcome"] for data in given.values()}:
        raise GradingError("the grading check needs a key that must pass and one that must fail")
    wrong = {}
    for name, data in given.items():
        problems = check(data["grading"], data["ids"], shared)
        right = not problems if data["outcome"] == "pass" else any(data["problem"] in p for p in problems)
        if not right:
            wrong[name] = problems
    return wrong
