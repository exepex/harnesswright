"""Grader runs (doc 11, Graders): one sealed grader run of one page, and the blind order of the pages of a round.

One rule: a grader is a trigger run of a folder that holds only the page and the questions. The runner starts it
through `host.run`, the one place a host runs, in the same jail, audit and gate as every run. A trigger run can
read its folder and write nothing the harness reads, so a grader sees one page and leaves nothing but its final
message, which is its answer sheet. The sheet is accepted only when `grading.check` finds no problem with it.

- `grade(adapter, page, asked, root)`: one page graded, with one more try when the host fails or the sheet is
  refused (`TRIES`). It returns the accepted sheet, or None with why, so the run is `ungraded`.
- `sheet(message)`: the grading file in a final message: the message is one JSON object, alone or as the one
  fenced block it holds, and nothing else.
- `blind(pages, seed)`: the order graders get the pages of a round, the runs of both arms and the goldens together,
  shuffled by a seed the round records. Each page gets an opaque id, the hash of its text, so no name of a run, an
  arm or a golden reaches a grader.

Standard library only.
"""

import hashlib
import json
import random
import re
import tempfile
from pathlib import Path

import contain
import grading
import host
import manifest

PROMPT = Path(__file__).resolve().parents[1] / "grading" / "prompt.md"
PAGE, QUESTIONS = "page.md", "questions.json"
TRIES = 2  # a refused sheet or a failed host gets one more try, as a voided slot gets one remake
FENCED = re.compile(r"```(?:json)?\n(.*)\n```", re.S)


class Graded:
    """One page's grading: `answers` ({id: "yes" or "no"}) when a sheet was accepted, else None, and `tries`, the
    reason of each try that gave no accepted sheet."""

    def __init__(self, answers, tries):
        self.answers, self.tries = answers, tries


def sheet(message):
    """The grading file a final message holds, or None. The message, stripped, is one JSON object, or one fenced
    block that holds one, and nothing else."""
    if not isinstance(message, str):
        return None
    text = message.strip()
    fenced = FENCED.fullmatch(text)
    try:
        found = json.loads(fenced.group(1) if fenced else text)
    except json.JSONDecodeError:
        return None
    return found if isinstance(found, dict) else None


def folder(root, page, asked):
    """A new grader folder under `root`, holding only the page and the questions. Its name is random, so it names
    no run, arm or golden."""
    made = Path(tempfile.mkdtemp(prefix="grader-", dir=root))
    world = made / "page"
    world.mkdir()
    (world / PAGE).write_text(page)
    (world / QUESTIONS).write_text(json.dumps(asked, indent=2, ensure_ascii=False) + "\n")
    return made, world


def grade(adapter, page, asked, root, model=None, timeout=900, prompt=None, **containment):
    """Grade `page` (`grading.page`) on the questions `asked` (`grading.questions`) with one grader of `adapter`'s
    host, in a containment under `root` (outside the repository). `prompt` replaces the grader prompt, as the fake
    host's actions do. `containment` passes on to `contain.Containment`. A broken jail or contract raises, as in
    every run: the round stops."""
    if not asked:
        return Graded({}, [])
    ids = [question["id"] for question in asked]
    text = PROMPT.read_text() if prompt is None else prompt
    tries = []
    for _ in range(TRIES):
        made, world = folder(root, page, asked)
        contained = contain.Containment(adapter, "trigger", world, manifest.manifest(world), root=made / "run",
                                        **containment)
        result = host.run(contained, text, skills=[], model=model, timeout=timeout)
        if result.failure:
            tries.append(f"the host failed: {result.failure}")
            continue
        messages = [item["text"] for item in result.log if item["kind"] == "message"]
        found = sheet(messages[-1] if messages else None)
        problems = ["the final message is not one JSON object"] if found is None else grading.check(found, ids, page)
        if not problems:
            return Graded({answer["id"]: answer["answer"] for answer in found["answers"]}, tries)
        tries.append("; ".join(problems))
    return Graded(None, tries)


def blind(pages, seed):
    """[(name, id)] for `pages` ({name: page text}) in the order graders get them: sorted by page hash, so the
    caller's order says nothing, then shuffled by `seed`. The id is the first 16 characters of the page's hash."""
    ids = {name: hashlib.sha256(text.encode()).hexdigest()[:16] for name, text in pages.items()}
    order = sorted(pages, key=lambda name: (ids[name], name))
    random.Random(seed).shuffle(order)
    return [(name, ids[name]) for name in order]
