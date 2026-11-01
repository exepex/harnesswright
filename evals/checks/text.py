"""Checks of the text a run wrote: a world file after the run (`file`, a world path), or, when `file` is left out,
the run's final message. A text that does not exist fails: the files after are the harness's own, and so is the
final message it took from the host's output.

One rule: every check that reads Markdown reads it through `lines`, which gives each line one kind. A line is
`frontmatter` (the leading `---` block of a file), `code` (a fenced block, from its opening fence to the closing
fence of the same character, at least as long, with nothing after it but spaces, or to the end), or `prose`. Each
check reads only the kinds it names, and a line it cannot read as one of the shapes it allows fails the check.

- `sections`: the ATX headings (`#` to `######`) of level `level` in prose lines are exactly `headings`, in that
  order, compared as written, inline code included.
- `frontmatter`: the text begins with a `---` block. Every line in it is blank, a `#` comment, indented or a `- `
  list item (part of the field above it), or `field: value`, where a field is letters, digits, `_` and `-`, given
  once; any other line fails. Its fields include each of `required`, hold none outside `allowed` when it is given,
  and give each field of `values` exactly that value (one line, quotes and a ` #` comment removed).
- `ends_with_one_question`: the prose, with inline code removed (a span may wrap), holds exactly one question, a
  `?` that ends a sentence, closed only by quotes, brackets or emphasis; and the text's last line that is not blank
  is prose and ends with it.
- `shares_words`: the text shares a run of `run` consecutive words with the world file `source` after the run
  (`shared` true), or shares none (`shared` false). Words are letters and digits, compared without case. Pair it
  with `file_state` `unchanged` on the source, so a run cannot change the reference.
"""

import re

from cases import is_path
from checks import Check

HEADING = re.compile(r" {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*")
OPEN = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
FIELD = re.compile(r"([A-Za-z0-9_-]+):(?:[ \t]+(.*))?")
CLOSERS = "\"')]*_~"
QUESTION = re.compile(r"\?[" + re.escape(CLOSERS) + r"]*(?=\s|$)")
WORD = re.compile(r"[^\W_]+")
QUOTED = re.compile(r"\s*([\"'])(.*?)\1\s*(?:#.*)?")
SPAN = re.compile(r"(`+)(?:(?!\n[ \t]*\n).)+?\1", re.DOTALL)  # inline code, which may wrap within a paragraph


def _text(bundle, file):
    text = bundle.final_message if file is None else bundle.text(file)
    return text, ("the final message" if file is None else file)


def lines(text, frontmatter):
    """[(kind, line)] of `text`: `frontmatter` for a leading `---` block when `frontmatter` is true, `code` for a
    fenced block, fences included, and `prose` for every other line."""
    found, fence, rows = [], None, text.splitlines()
    end = next((i for i, row in enumerate(rows[1:], 1) if row.rstrip() == "---"), None) \
        if frontmatter and rows and rows[0].rstrip() == "---" else None
    for number, row in enumerate(rows):
        if end is not None and number <= end:
            found.append(("frontmatter", row))
            continue
        opened = OPEN.fullmatch(row)
        if fence is None and opened and not (opened.group(1)[0] == "`" and "`" in opened.group(2)):
            fence = opened.group(1)
            found.append(("code", row))
        elif fence is not None:
            if opened and opened.group(1)[0] == fence[0] and len(opened.group(1)) >= len(fence) \
                    and not opened.group(2).strip():
                fence = None
            found.append(("code", row))
        else:
            found.append(("prose", row))
    return found


def sections(bundle, headings, level, file=None):
    text, name = _text(bundle, file)
    if text is None:
        return "fail", f"{name} does not exist"
    found = [(m.group(2) or "") for kind, row in lines(text, file is not None) if kind == "prose"
             for m in [HEADING.fullmatch(row)] if m and len(m.group(1)) == level]
    if found == headings:
        return "pass", f"{name} has the level {level} headings {headings}, in order"
    return "fail", f"{name} has the level {level} headings {found[:20]}, and the expectation is {headings}"


def _value(raw):
    quoted = QUOTED.fullmatch(raw or "")
    return quoted.group(2) if quoted else re.sub(r"\s+#.*$", "", (raw or "").strip())


def frontmatter(bundle, required, allowed=None, values=None, file=None):
    text, name = _text(bundle, file)
    if text is None:
        return "fail", f"{name} does not exist"
    block = [row for kind, row in lines(text, True) if kind == "frontmatter"]
    if len(block) < 2:
        return "fail", f"{name} does not begin with a frontmatter block between --- lines"
    fields = {}
    for number, row in enumerate(block[1:-1], 2):
        field = FIELD.fullmatch(row.rstrip())
        if field and field.group(1) not in fields:
            fields[field.group(1)] = _value(field.group(2))
        elif field or not (not row.strip() or row.lstrip().startswith("#") or row[0] in " \t"
                           or row.startswith("- ") and fields):
            return "fail", f"{name}'s frontmatter line {number} is not a field given once: {row[:200]}"
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
    read = lines(text, file is not None)
    prose = SPAN.sub("", "\n".join(row if kind == "prose" else "" for kind, row in read)).rstrip()
    asked = QUESTION.findall(prose)
    filled = [kind for kind, row in read if row.strip()]
    last = bool(filled) and filled[-1] == "prose" and prose.rstrip(CLOSERS).endswith("?")
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
