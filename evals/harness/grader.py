"""Grader runs (doc 11, Graders): one sealed grader run of one page, and the blind order of the pages of a round.

One rule: a grader is a trigger run of a folder that holds only the page and the questions. The runner starts it
through `host.run`, the one place a host runs, in the same jail, audit and gate as every run. A trigger run can
read its folder and write nothing the harness reads, so a grader sees one page and leaves nothing but its final
message, which is its answer sheet. The sheet is accepted only when `grading.check` finds no problem with it.

- `grade(adapter, page, asked)`: one page graded, with one more try when the host fails or the sheet is refused
  (`TRIES`). It returns the accepted sheet, or None with why, so the run is `ungraded`. `grade` alone chooses where
  a grader's folder is, since a grader starts in it and sees its whole path: a new folder of random name in the
  operator's temp folder (`place`), the same for every page of a round, so the path tells no run, arm or golden
  from another. The folder is removed after the try, once the run's log and reasons have passed its scrub
  (`scrub.Scrub.of_run`), so what a grader printed keeps no credential and a canary in it stops the round.
- `sheet(message)`: the grading file in a final message: the message is one JSON object, alone or as the one
  fenced block it holds, and nothing else. A line break inside a string is read as it stands.
- `blind(pages, seed)`: the order graders get the pages of a round, the runs of both arms and the goldens together,
  mixed by a seed the round records. Each page gets an opaque id, the hash of its text, so no name of a run, an
  arm or a golden reaches a grader.

Standard library only.
"""

import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

import contain
import evidence
import grading
import host
import manifest
import scrub as scrubs

PROMPT = Path(__file__).resolve().parents[1] / "grading" / "prompt.md"
PAGE, QUESTIONS = "page.md", "questions.json"
TRIES = 2  # a refused sheet or a failed host gets one more try, as a voided slot gets one remake
FENCED = re.compile(r"```(?:json)?[ \t]*\r?\n(.*)\r?\n```", re.S | re.I)


class Graded:
    """One page's grading: `sheet`, the accepted answer sheet whole, with its quotes, or None; `answers` ({id: "yes"
    or "no"}) from it, or None; `tries`, the reason of each try that gave no accepted sheet; and `logs`, the action
    log of each try's host run, in order, for the round's record and its faults."""

    def __init__(self, sheet, tries, logs):
        self.sheet, self.tries, self.logs = sheet, tries, logs
        self.answers = None if sheet is None else {answer["id"]: answer["answer"] for answer in sheet["answers"]}


def sheet(message):
    """The grading file a final message holds, or None. The message, stripped, is one JSON object, or one fenced
    block that holds one, and nothing else."""
    if not isinstance(message, str):
        return None
    text = message.strip()
    fenced = FENCED.fullmatch(text)
    try:
        found = json.loads(fenced.group(1) if fenced else text, strict=False)
    except json.JSONDecodeError:
        return None
    return found if isinstance(found, dict) else None


def place():
    """Where every grader folder is made: the operator's temp folder, which is the same for every page."""
    return Path(tempfile.gettempdir())


def folder(page, asked):
    """A new grader folder in `place()`, holding only the page and the questions. Its path is that place and a
    random name, so it tells no run, arm or golden from another."""
    made = Path(tempfile.mkdtemp(prefix="grader-", dir=place()))
    world = made / "page"
    world.mkdir()
    (world / PAGE).write_text(page)
    (world / QUESTIONS).write_text(json.dumps(asked, indent=2, ensure_ascii=False) + "\n")
    return made, world


def grade(adapter, page, asked, model=None, timeout=900, prompt=None, **containment):
    """Grade `page` (`grading.page`) on the questions `asked` (`grading.questions`) with one grader of `adapter`'s
    host, in a grader folder (`folder`). `prompt` replaces the grader prompt, as the fake host's actions do.
    `containment` passes on to `contain.Containment`. A broken jail or contract raises, as in every run: the round
    stops."""
    if not asked:
        return Graded({"answers": []}, [], [])
    ids = [question["id"] for question in asked]
    text = PROMPT.read_text() if prompt is None else prompt
    tries, logs = [], []
    for _ in range(TRIES):
        made, world = folder(page, asked)
        try:
            contained = contain.Containment(adapter, "trigger", world, manifest.manifest(world), root=made / "run",
                                            **containment)
            result = host.run(contained, text, skills=[], model=model, timeout=timeout)
            clean = scrubs.Scrub.of_run(contained)  # made while the home is there, so a refreshed credential counts
            log = evidence.scrubbed_log(clean, result.log, "grader/log")
        finally:
            shutil.rmtree(made, ignore_errors=True)
        logs.append(log)
        if result.failure:
            tries.append(clean.text(f"the host failed: {result.failure}", "grader/failure"))
            continue
        messages = [item["text"] for item in log if item["kind"] == "message"]
        found = sheet(messages[-1] if messages else None)
        problems = ["the final message is not one JSON object"] if found is None else grading.check(found, ids, page)
        if not problems:
            return Graded(found, tries, logs)
        tries.append(clean.text("; ".join(problems), "grader/problems"))
    return Graded(None, tries, logs)


def blind(pages, seed):
    """[(name, id)] for `pages` ({name: page text}) in the order graders get them. The id is the first 16
    characters of the page's hash. The order is by the hash of the seed with the id, so it depends on the seed and
    the pages alone, never on the caller's names or order, and the same seed gives the same order again."""
    ids = {name: hashlib.sha256(text.encode()).hexdigest()[:16] for name, text in pages.items()}
    return [(name, ids[name]) for name in sorted(
        pages, key=lambda name: (hashlib.sha256(f"{seed}:{ids[name]}".encode()).hexdigest(), name))]
