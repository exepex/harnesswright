"""Grader runs (doc 11, Graders): one sealed grader run of one page, and the blind order of the pages of a round.

One rule: a grader is a trigger run of a folder that holds only the page and the questions. The runner starts it
through `host.run`, the one place a host runs, in the same jail, audit and gate as every run. A trigger run can
read its folder and write nothing the harness reads, so a grader sees one page and leaves nothing but its final
message, which is its answer sheet. The sheet is accepted only when `grading.check` finds no problem with it.

- `grade(adapter, page, asked)`: one page graded, with one more try when the host fails or the sheet is refused
  (`TRIES`). It returns the accepted sheet, or None with why, so that grader is ungraded. `grade` alone chooses where
  a grader's folder is, since a grader starts in it and sees its whole path: a new folder of random name in the
  operator's temp folder (`place`), the same for every page of a round, so the path tells no run, arm or golden
  from another. The folder is removed after the try, once everything the run made outside it has passed
  `evidence.reported`, the one way every run's output is scrubbed and checked for canaries, so a grader leaves no
  credential and a canary stops the round.
- `sheet(message)`: the grading file in a final message: the JSON object the message ends with, alone or in one
  fenced block. Text before it is ignored, since a grader may say a sentence first; text after it refuses. A line
  break inside a string is read as it stands. Each refused message is kept, scrubbed and cut to `KEPT` characters,
  so the next refusal can be read from the store.
- `panel(page, asked, graders, tiebreak)`: one page's answers from a panel of graders, by one rule: a question's
  answer is the one two graders gave. Two graders grade the page, on two different hosts when both are available
  (the caller chooses them). A question they answered two ways goes to one fresh grader on the reference host
  (`tiebreak`). A grader with no sheet is replaced once by a fresh grader of its own host, which answers every
  question. A question that has no two answers the same, as when that grader is ungraded too, is unanswered, so the
  run stays ungraded on it: one grader never decides a question alone. Agreement of the two graders is reported,
  never used as a gate.
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
OPENING = re.compile(r"(?:^|\n)```(?:json)?[ \t]*\r?\n", re.I)  # the line that opens a fenced block
KEPT = 4000  # characters of a refused message the grade record keeps


class Graded:
    """One page's grading: `sheet`, the accepted answer sheet whole, with its quotes, or None; `answers` ({id: "yes"
    or "no"}) from it, or None; `tries`, the reason of each try that gave no accepted sheet; `refused`, the final
    message of each refused sheet, scrubbed and cut to `KEPT` characters; `logs`, the action log of each try's host
    run, in order, for the round's record and its faults; and `costs`, each try's seconds and token counts by model
    as the host reported them (`host.Result`), in the same order."""

    def __init__(self, sheet, tries, logs, costs=(), refused=()):
        self.sheet, self.tries, self.logs, self.costs = sheet, tries, logs, list(costs)
        self.refused = list(refused)
        self.answers = None if sheet is None else {answer["id"]: answer["answer"] for answer in sheet["answers"]}


def sheet(message):
    """The grading file a final message holds, or None: the JSON object the stripped message ends with. When the
    message ends with a fenced block, it is the whole of the last block. Otherwise it starts at the first `{` from
    which one JSON value runs to the end of the message. Text before it is ignored."""
    if not isinstance(message, str):
        return None
    text = message.strip()
    decoder = json.JSONDecoder(strict=False)
    if text.endswith("```"):
        opened = list(OPENING.finditer(text[:-3]))
        if not opened:
            return None
        body = text[opened[-1].end():-3].strip()
        try:
            found, end = decoder.raw_decode(body)
        except json.JSONDecodeError:
            return None
        return found if end == len(body) and isinstance(found, dict) else None
    for start in (i for i, char in enumerate(text) if char == "{"):
        try:
            found, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if end == len(text):
            return found if isinstance(found, dict) else None
    return None


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


def grade(adapter, page, asked, model=None, timeout=900, prompt=None, watch=None, **containment):
    """Grade `page` (`grading.page`) on the questions `asked` (`grading.questions`) with one grader of `adapter`'s
    host, in a grader folder (`folder`). `prompt` replaces the grader prompt, as the fake host's actions do. `watch`,
    when given, is called with each try's containment, folder and reported run (None when the run raised) before
    the folder goes, as the grader faults look at them.
    `containment` passes on to `contain.Containment`. A broken jail or contract raises, as in every run: the round
    stops."""
    if not asked:
        return Graded({"answers": []}, [], [])
    ids = [question["id"] for question in asked]
    text = PROMPT.read_text() if prompt is None else prompt
    tries, logs, costs, refused = [], [], [], []
    for _ in range(TRIES):
        made, world = folder(page, asked)
        contained = ran = None
        try:
            contained = contain.Containment(adapter, "trigger", world, manifest.manifest(world), root=made / "run",
                                            **containment)
            result = host.run(contained, text, skills=[], model=model, timeout=timeout)
            clean = scrubs.Scrub.of_run(contained)  # made before the folder goes, so a refreshed credential counts
            ran, _ = evidence.reported(contained, result, clean, "grader")
        finally:
            try:
                if watch is not None and contained is not None:
                    watch(contained, made, ran)
            finally:  # the folder goes even when the watch fails, as it holds the host's copied files
                shutil.rmtree(made, ignore_errors=True)
        logs.append(ran["log"])
        costs.append({"seconds": result.seconds, "tokens": result.tokens})
        if ran["failure"]:
            tries.append(f"the host failed: {ran['failure']}")
            continue
        found = sheet(ran["final_message"])
        problems = (["the final message does not end with one JSON object"] if found is None
                    else grading.check(found, ids, page))
        if not problems:
            return Graded(found, tries, logs, costs, refused)
        tries.append(clean.text("; ".join(problems), "grader/problems"))
        refused.append((ran["final_message"] or "")[:KEPT])  # scrubbed by evidence.reported
    return Graded(None, tries, logs, costs, refused)


class Panel:
    """One page's grading by a panel: `answers` ({id: "yes" or "no"}) for the questions two graders answered the
    same; `unanswered`, the ids of the rest, in order; `agreed`, how many questions the two graders answered the same,
    of `asked`; and `graded`, each grader's `Graded`, the tie-breaker last when it ran."""

    def __init__(self, answers, unanswered, agreed, asked, graded):
        self.answers, self.unanswered, self.agreed, self.asked, self.graded = answers, unanswered, agreed, asked, graded


def panel(page, asked, graders, tiebreak):
    """Grade `page` on the questions `asked` with the two `graders` and, for the questions they answered two ways,
    the `tiebreak` grader. Each grader is a function of (page, questions) that gives a `Graded`, such as `grade`
    bound to one host; each call is a fresh grader. A grader with no sheet is replaced once by a fresh grader of its
    own host, which answers every question, so the two sheets still come from the two hosts; its failed tries are
    kept. A question that has no two answers the same stays unanswered: one grader never decides alone."""
    if len(graders) != 2:
        raise ValueError("a panel has two graders, and a tie-breaker")
    graded = [grade_one(page, asked) for grade_one in graders]
    for number, grade_one in enumerate(graders):
        if graded[number].answers is None:
            fresh, failed = grade_one(page, asked), graded[number]
            graded[number] = Graded(fresh.sheet, failed.tries + fresh.tries, failed.logs + fresh.logs,
                                    failed.costs + fresh.costs)
    votes = {question["id"]: [g.answers[question["id"]] for g in graded if g.answers] for question in asked}
    same = {id_ for id_, given in votes.items() if len(given) == 2 and given[0] == given[1]}
    disputed = [question for question in asked if len(set(votes[question["id"]])) == 2]  # both answered, two ways
    if disputed:
        graded.append(tiebreak(page, disputed))
        for question in disputed:
            if graded[-1].answers:
                votes[question["id"]].append(graded[-1].answers[question["id"]])
    answers = {}
    for id_, given in votes.items():
        answers.update({id_: answer for answer in grading.ANSWERS if given.count(answer) >= 2})
    unanswered = [question["id"] for question in asked if question["id"] not in answers]
    return Panel(answers, unanswered, len(same), len(asked), graded)


def digest(page, asked):
    """{"page", "questions"}: the sha256 of a page's text and of its questions, as a grade record keeps them, so a page
    rebuilt later, from its stored bundle, can be shown to be the page that was graded, on the same questions."""
    questions = json.dumps(asked, sort_keys=True, ensure_ascii=False)
    texts = {"page": page, "questions": questions}
    return {name: hashlib.sha256(text.encode()).hexdigest() for name, text in texts.items()}


def blind(pages, seed):
    """[(name, id)] for `pages` ({name: page text}) in the order graders get them. The id is the first 16
    characters of the page's hash. The order is by the hash of the seed with the id, so it depends on the seed and
    the pages alone, never on the caller's names or order, and the same seed gives the same order again."""
    ids = {name: hashlib.sha256(text.encode()).hexdigest()[:16] for name, text in pages.items()}
    return [(name, ids[name]) for name in sorted(
        pages, key=lambda name: (hashlib.sha256(f"{seed}:{ids[name]}".encode()).hexdigest(), name))]
