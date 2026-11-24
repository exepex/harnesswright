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
- `sheet(message)`: the grading file in a final message: the JSON object the message ends with, after any closing
  fence. Text before it is ignored, since a grader may say a sentence or open a fence first; text after it refuses.
  A line break inside a string is read as it stands. Each try keeps its final message, scrubbed and cut to `KEPT`
  characters, so the next refusal can be read from the store.
- `panel(page, asked, graders, tiebreak)`: one page's answers from a panel of graders, by one rule: a question's
  answer is the one two graders gave. Two graders grade the page, on two different hosts when both are available
  (the caller chooses them). A question they answered two ways goes to one fresh grader on the reference host
  (`tiebreak`). A grader with no sheet is replaced once by a fresh grader of its own host, which answers every
  question. A question that has no two answers the same, as when that grader is ungraded too, is unanswered, so the
  run stays ungraded on it: one grader never decides a question alone. A question a grader answered two ways across
  its tries, a refused sheet's answers counting (`given`), is a retry that flipped (`flipped`): it stays unanswered
  on that page alone. Agreement of the two graders is reported, never used as a gate.
- `blind(pages, seed)`: the order graders get the pages of a round, the runs of both arms and the goldens together,
  mixed by a seed the round records. Each page gets an opaque id, the hash of its text, so no name of a run, an
  arm or a golden reaches a grader.

Standard library only.
"""

import hashlib
import json
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
KEPT = 4000  # characters of a refused message the grade record keeps


class Graded:
    """One page's grading: `sheet`, the accepted answer sheet whole, with its quotes, or None; `answers` ({id: "yes"
    or "no"}) from it, or None; `tries`, the reason of each try that gave no accepted sheet; `refused`, beside each of
    `tries`, that try's final message, scrubbed and cut to `KEPT` characters, or None when the host failed; `logs`,
    the action log of each try's host run, in order, for the round's record and its faults; `costs`, each try's
    seconds and token counts by model as the host reported them (`host.Result`), in the same order; and `offered`,
    beside each of `tries`, every answer its refused sheet gave ({id: ["yes" or "no", ...]}, duplicates kept), or
    None, which count in agreement and show a retry that flipped (`flipped`)."""

    def __init__(self, sheet, tries, logs, costs=(), refused=None, offered=None):
        self.sheet, self.tries, self.logs, self.costs = sheet, tries, logs, list(costs)
        self.refused = [None] * len(tries) if refused is None else list(refused)
        self.offered = [None] * len(tries) if offered is None else list(offered)
        self.answers = None if sheet is None else {answer["id"]: answer["answer"] for answer in sheet["answers"]}


def sheet(message):
    """The grading file a final message holds, or None: the JSON object the stripped message ends with, after any
    closing fence. It starts at the first `{` from which one JSON value runs to the end. Text before it, an opening
    fence among it, is ignored; a fence inside a quote is part of the quote."""
    if not isinstance(message, str):
        return None
    text = message.strip()
    if text.endswith("```"):
        text = text[:-3].rstrip()
    decoder = json.JSONDecoder(strict=False)
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
    tries, logs, costs, refused, offered = [], [], [], [], []
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
            refused.append(None)
            offered.append(None)
            continue
        found = sheet(ran["final_message"])
        problems = (["the final message does not end with one JSON object"] if found is None
                    else grading.check(found, ids, page))
        if not problems:
            return Graded(found, tries, logs, costs, refused, offered)
        tries.append(clean.text("; ".join(problems), "grader/problems"))
        refused.append((ran["final_message"] or "")[:KEPT])  # scrubbed by evidence.reported
        offered.append(given(found, ids))
    return Graded(None, tries, logs, costs, refused, offered)


def given(found, ids):
    """Every answer ({id: ["yes" or "no", ...]}, in order) a refused sheet `found` gave to the questions `ids`, a
    duplicate kept, or None when it gave none: a sheet refused for its form still says how its grader answered."""
    answers = found.get("answers") if isinstance(found, dict) else None
    kept = {}
    for a in answers if isinstance(answers, list) else []:
        if isinstance(a, dict) and a.get("id") in ids and a.get("answer") in grading.ANSWERS:
            kept.setdefault(a["id"], []).append(a["answer"])
    return kept or None


def flipped(graded):
    """The ids of the questions one grader (`Graded`, with its retries and its fresh replacement) gave more than one
    answer across its tries and their duplicates: a retry that flipped, so that page's answer to it is not settled."""
    found = {}
    for answers in [*graded.offered, {id_: [answer] for id_, answer in (graded.answers or {}).items()}]:
        for id_, said in (answers or {}).items():
            found.setdefault(id_, set()).update(said)
    return sorted(id_ for id_, seen in found.items() if len(seen) > 1)


class Panel:
    """One page's grading by a panel: `answers` ({id: "yes" or "no"}) for the questions it settled; `unanswered`, the
    ids of the rest, in order; `agreed`, how many questions the two graders answered the same, of `asked`; `graded`,
    each grader's `Graded`, the tie-breaker last when it ran; and `flipped`, the ids a grader's retry flipped."""

    def __init__(self, answers, unanswered, agreed, asked, graded, flipped=()):
        self.answers, self.unanswered, self.agreed, self.asked, self.graded = answers, unanswered, agreed, asked, graded
        self.flipped = list(flipped)


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
                                    failed.costs + fresh.costs, failed.refused + fresh.refused,
                                    failed.offered + fresh.offered)
    votes = {question["id"]: [g.answers[question["id"]] for g in graded if g.answers] for question in asked}
    same = {id_ for id_, given in votes.items() if len(given) == 2 and given[0] == given[1]}
    disputed = [question for question in asked if len(set(votes[question["id"]])) == 2]  # both answered, two ways
    if disputed:
        graded.append(tiebreak(page, disputed))
        for question in disputed:
            if graded[-1].answers:
                votes[question["id"]].append(graded[-1].answers[question["id"]])
    turned = sorted({id_ for g in graded for id_ in flipped(g)})  # a flipped retry leaves its question unsettled
    answers = {}
    for id_, votes_ in votes.items():
        if id_ not in turned:
            answers.update({id_: answer for answer in grading.ANSWERS if votes_.count(answer) >= 2})
    unanswered = [question["id"] for question in asked if question["id"] not in answers]
    return Panel(answers, unanswered, len(same), len(asked), graded, turned)


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
