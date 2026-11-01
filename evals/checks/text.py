"""Checks of the text a run wrote: a world file after the run (`file`, a world path), or, when `file` is left out,
the run's final message. A text that does not exist fails: the files after are the harness's own, and so is the
final message it took from the host's output.

- `sections`: the Markdown headings (`#` to `######`, outside code fences) of level `level` are exactly
  `headings`, in that order, and no other heading of that level.
- `frontmatter`: the text begins with a `---` block whose top-level fields include each of `required`, hold none
  outside `allowed` when it is given, and give each field of `values` exactly that one-line value.
- `ends_with_one_question`: the text, outside code, holds exactly one question, a `?` that ends a sentence, and it
  is the last thing in the text.
- `shares_words`: the text shares a run of `run` consecutive words with the world file `source` (`shared` true), or
  shares none (`shared` false). Words are letters and digits, compared without case.
"""

import re

from cases import is_path
from checks import Check

HEADING = re.compile(r" {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*")
FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
FIELD = re.compile(r"([A-Za-z0-9_-]+):(.*)")
QUESTION = re.compile(r"\?+(?=[\"')\]]*(?:\s|$))")
WORD = re.compile(r"[^\W_]+")


def _text(bundle, file):
    text = bundle.final_message if file is None else bundle.text(file)
    name = "the final message" if file is None else file
    return text, name


def _prose(text):
    """The lines of `text` outside code fences, with inline code removed."""
    lines, fence = [], None
    for line in text.splitlines():
        opened = FENCE.match(line)
        if opened and (fence is None or opened.group(1)[0] == fence[0] and len(opened.group(1)) >= len(fence)):
            fence = opened.group(1) if fence is None else None
            continue
        if fence is None:
            lines.append(re.sub(r"`+[^`]*`+", "", line))
    return lines


def sections(bundle, headings, level, file=None):
    text, name = _text(bundle, file)
    if text is None:
        return "fail", f"{name} does not exist"
    found = [m.group(2) for m in map(HEADING.fullmatch, _prose(text)) if m and len(m.group(1)) == level]
    if found == headings:
        return "pass", f"{name} has the level {level} headings {headings}, in order"
    return "fail", f"{name} has the level {level} headings {found[:20]}, and the expectation is {headings}"


def frontmatter(bundle, required, allowed=None, values=None, file=None):
    text, name = _text(bundle, file)
    if text is None:
        return "fail", f"{name} does not exist"
    lines = text.splitlines()
    end = next((i for i, line in enumerate(lines[1:], 1) if line.rstrip() == "---"), None)
    if not lines or lines[0].rstrip() != "---" or end is None:
        return "fail", f"{name} does not begin with a frontmatter block between --- lines"
    fields = {}
    for line in lines[1:end]:
        field = FIELD.fullmatch(line.rstrip())
        if field:
            fields[field.group(1)] = field.group(2).strip().strip("\"'")
    missing = [f for f in required if f not in fields]
    extra = [f for f in fields if allowed is not None and f not in allowed]
    wrong = [f for f, value in (values or {}).items() if fields.get(f) != value]
    if missing or extra or wrong:
        return "fail", (f"{name}'s frontmatter fields are {sorted(fields)}: {missing} are missing, {extra} are not "
                        f"allowed, and {wrong} do not hold {values or {}}")
    return "pass", f"{name}'s frontmatter fields are {sorted(fields)}, as the expectation says"


def ends_with_one_question(bundle, file=None):
    text, name = _text(bundle, file)
    if text is None:
        return "fail", f"{name} does not exist"
    prose = "\n".join(_prose(text)).rstrip()
    asked = QUESTION.findall(prose)
    last = prose.rstrip("\"')]").endswith("?")
    if len(asked) == 1 and last:
        return "pass", f"{name} ends with its one question"
    return "fail", f"{name} holds {len(asked)} questions, and {'ends' if last else 'does not end'} with one"


def shares_words(bundle, source, run, shared, file=None):
    text, name = _text(bundle, file)
    original = bundle.text(source)
    if text is None or original is None:
        return "fail", f"{name if text is None else source} does not exist"
    words = [w.lower() for w in WORD.findall(original)]
    runs = {tuple(words[i:i + run]) for i in range(len(words) - run + 1)}
    mine = [w.lower() for w in WORD.findall(text)]
    common = next((mine[i:i + run] for i in range(len(mine) - run + 1) if tuple(mine[i:i + run]) in runs), None)
    if common:
        return ("pass" if shared else "fail"), f"{name} shares {run} words with {source}: {' '.join(common)[:200]}"
    return ("fail" if shared else "pass"), f"{name} shares no run of {run} words with {source}"


def is_texts(value):
    return isinstance(value, list) and bool(value) and all(isinstance(v, str) and v for v in value)


def is_count(value, low=1, high=None):
    return isinstance(value, int) and not isinstance(value, bool) and low <= value and (high is None or value <= high)


def is_values(value):
    return isinstance(value, dict) and bool(value) and all(isinstance(v, str) for v in value.values())


FILE = {"file": is_path}
CHECKS = {
    "sections": Check(sections, {"headings": is_texts, "level": lambda v: is_count(v, 1, 6), **FILE},
                      optional=("file",), about="the headings of one level are exactly these, in order"),
    "frontmatter": Check(frontmatter, {"required": is_texts, "allowed": is_texts, "values": is_values, **FILE},
                         optional=("allowed", "values", "file"),
                         about="the frontmatter holds these fields, only allowed ones, with these values"),
    "ends_with_one_question": Check(ends_with_one_question, dict(FILE), optional=("file",),
                                    about="the text holds exactly one question, and ends with it"),
    "shares_words": Check(shares_words, {"source": is_path, "run": is_count, "shared": lambda v: isinstance(v, bool),
                                         **FILE},
                          optional=("file",), about="the text shares a run of words with a source file, or none"),
}
