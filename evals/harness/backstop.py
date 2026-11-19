"""The baseline backstop (doc 11, Baseline backstop): a without-skill run whose evidence holds a long passage of the
skill's own text saw the skill, so the run is void.

One rule: a hit is one unbroken span of at least `SPAN` words, inside one text of the run, in which every run of
`textruns.RUN` words is one of the skill's own runs (`protected`). The skill's own runs are the lint's
(`lint.protected`): its text minus the project text the run may see. Matches in different texts, or the same words
found again, never add up. A shorter match is a phrase an honest agent reaches by itself, such as a common script
header, so it is listed, never a void.

- `protected(case, arm, skill_dir, repo)`: the skill's own runs for the built without-skill `arm` of `case`.
- `texts(record, blob)`: the texts of a stored run: its final message, each file it changed, the string values of
  each transcript line, and the string values of each action log entry (a host such as Codex reports sub-agents
  only there), so words never run together across lines or values.
- `matches(protected, texts)`: every distinct span of the skill's own runs, long or short, in order.
- `check(record, blob, protected)`: {"void": the spans of at least `SPAN` words, "short": the others}.

`runs.run` checks every without-skill run through `check`, after its evidence is collected (so a canary stops the
round first); the backstop fault checks its plant through the same function. Standard library only.
"""

import json
from pathlib import Path

import lint
import manifest
from textruns import RUN, words

SPAN = 16  # words: a span this long has 9 of the skill's own runs in a row


def protected(case, arm, skill_dir, repo):
    """The skill's own runs for the built without-skill `arm` of `case`, as the lint protects them."""
    repo = Path(repo)
    copied, _ = lint.verified_copies(case, repo)
    upstream = lint.texts(repo / "evals" / "skills" / case.skill / "upstream")
    return lint.protected(case, lint.visible(case, arm), copied, skill_dir, upstream, repo)[1]


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def texts(record, blob):
    """[(where, text)] of a stored run: `record` and `blob` as `evidence.load` gives them."""
    found = [("final message", record["final_message"] or "")]
    for path, change in sorted(record["diff"].items()):
        entry = change["after"]
        if entry and manifest.is_file(entry):
            found.append((f"world/{path}", blob(entry.split(" ")[1]).decode("utf-8", "replace")))
    for name, digest in sorted(record["transcript"].items()):
        for number, line in enumerate(blob(digest).decode("utf-8", "replace").splitlines(), 1):
            try:
                parts = list(_strings(json.loads(line)))
            except ValueError:
                parts = [line]
            found += [(f"{name} line {number}", part) for part in parts]
    for number, item in enumerate(record["log"]):
        found += [(f"log {number}", part) for part in _strings(item)]
    return found


def matches(protected, texts):
    """[(where, words, span)]: each distinct span of consecutive words whose every `RUN`-word run is protected, with
    the first place it was found and its length in words."""
    seen, found = set(), []
    for where, text in texts:
        said = words(text)
        own = [" ".join(said[i:i + RUN]) in protected for i in range(len(said) - RUN + 1)]
        start = None
        for i, hit in enumerate(own + [False]):
            if hit and start is None:
                start = i
            elif not hit and start is not None:
                span = " ".join(said[start:i - 1 + RUN])
                if span not in seen:
                    seen.add(span)
                    found.append((where, i - 1 + RUN - start, span))
                start = None
    return found


def check(record, blob, protected, where=None):
    """{"void": [...], "short": [...]}: the spans of `matches` of at least `SPAN` words, and the others. `where`
    keeps the texts of `texts` to that one place (the backstop fault proves a planted place with it)."""
    found = matches(protected, [t for t in texts(record, blob) if where is None or t[0] == where])
    return {"void": [m for m in found if m[1] >= SPAN], "short": [m for m in found if m[1] < SPAN]}
