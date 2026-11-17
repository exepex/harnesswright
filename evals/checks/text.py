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
- `no_shared_words`: no file the run added or changed that matches one of the globs in `written` (`*` crosses
  folders), the source left out, shares a run of `run` words with the world file `source` after the run, compared
  as `shares_words` compares them. A `.json` file that parses (after any byte order mark) is read as its decoded
  keys and strings, as a reader sees them, so an escape such as `\\n` never joins two words; the source is read
  the same way. A file the run did not touch is not read, any other entry it wrote there (a link) fails, and no
  written file at all passes, so a case pairs it with a check that the run wrote.
- `field_words`: the frontmatter, read as `frontmatter` reads it, has the field `field`, and its value holds at most
  `most` words, counted as `shares_words` counts them: the field's own value, read as `frontmatter` reads it, and
  every indented line under it, as written (in a `>` or `|` block a `#` is text).
- `line_counts`: the section under the prose heading `section` (to the next heading of its level or above) is a
  listing: every line that is not blank is only `` - `path` (N lines) `` (or `1 line`) or `` - `path` (deleted) ``,
  and there is at least one. Any other line there, a code block included, fails. Each listed file is a file after
  the run with exactly N lines, counted as its newline characters (as `wc -l` counts), and each file listed
  deleted is absent.
- `line_references`: every reference in the writer's own prose points at lines that exist in its file after the
  run: 1 <= N <= M <= its line count, where a last line without a line feed counts. A reference is an inline code
  span that is only `path:N` or `path:N-M` and names something in the world before or after the run: its first part
  is a world entry, or its last part is the name of one. The world is the list of what can be cited, and a
  reference gives the file's whole path from the world's root, so `src/gone.py:2` (when `src` was there) and
  `app.py:2` (when the file is `src/app.py`) are broken, as is any other spelling, such as `./src/app.py:2`, and
  `localhost:8080` is not a reference. Quoted lines (`>`, such as the quoted story) are someone else's words and
  are not read. A file `line_counts` lists is also only ever a world path.
"""

import json
import re

from cases import is_path
from checks import Check, is_globs, matches

HEADING = re.compile(r" {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*")
OPEN = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
FIELD = re.compile(r"([A-Za-z0-9_-]+):(?:[ \t]+(.*))?")
CLOSERS = "\"')]*_~"
QUESTION = re.compile(r"\?[" + re.escape(CLOSERS) + r"]*(?=\s|$)")
WORD = re.compile(r"[^\W_]+")
ENTRY = re.compile(r"[ \t]*[-*][ \t]+`([^`]+)`[ \t]+\((?:(\d+) lines?|(deleted))\)[ \t]*")
REFERENCE = re.compile(r"([^\s:`]+):(\d+)(?:-(\d+))?")
QUOTE = re.compile(r" {0,3}>")
QUOTED = re.compile(r"\s*([\"'])(.*?)\1\s*(?:#.*)?")
# Inline code: a whole run of backticks, to the next run of the same length; it may wrap within a paragraph.
SPAN = re.compile(r"(?<!`)(`+)(?!`)(?:(?!\n[ \t]*\n).)+?(?<!`)\1(?!`)", re.DOTALL)


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


def _prose(text, frontmatter):
    """The rows of `text`, each prose row as written and every other row empty, so row N is still line N."""
    return [row if kind == "prose" else "" for kind, row in lines(text, frontmatter)]


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


def _fields(text, name):
    """({field: rows}, None) of the frontmatter block of `text`, where a field's rows are its own line's value and
    every indented or `- ` line under it, as written; or (None, why it fails). An indented line above the first
    field belongs to no field."""
    block = [row for kind, row in lines(text, True) if kind == "frontmatter"]
    if len(block) < 2:
        return None, f"{name} does not begin with a frontmatter block between --- lines"
    fields, last = {}, None
    for number, row in enumerate(block[1:-1], 2):
        field = FIELD.fullmatch(row.rstrip())
        if field and field.group(1) not in fields:
            last = field.group(1)
            fields[last] = [field.group(2) or ""]
        elif field or not (not row.strip() or row.lstrip().startswith("#") or row[0] in " \t"
                           or row.startswith("- ") and fields):
            return None, f"{name}'s frontmatter line {number} is not a field given once: {row[:200]}"
        elif last is not None and row.strip() and (row[0] in " \t" or row.startswith("- ")):
            fields[last].append(row)
    return fields, None


def frontmatter(bundle, required, allowed=None, values=None, file=None):
    text, name = _text(bundle, file)
    if text is None:
        return "fail", f"{name} does not exist"
    rows, why = _fields(text, name)
    if rows is None:
        return "fail", why
    fields = {field: _value(given[0]) for field, given in rows.items()}
    missing = [f for f in required if f not in fields]
    extra = [f for f in fields if allowed is not None and f not in allowed]
    wrong = [f for f, value in (values or {}).items() if fields.get(f) != value]
    if missing or extra or wrong:
        return "fail", (f"{name}'s frontmatter fields are {sorted(fields)}: {missing} are missing, {extra} are not "
                        f"allowed, and {wrong} do not hold {values or {}}")
    return "pass", f"{name}'s frontmatter fields are {sorted(fields)}, as the expectation says"


def field_words(bundle, field, most, file=None):
    text, name = _text(bundle, file)
    if text is None:
        return "fail", f"{name} does not exist"
    rows, why = _fields(text, name)
    if rows is None:
        return "fail", why
    if field not in rows:
        return "fail", f"{name}'s frontmatter has no field {field}"
    count = len(WORD.findall(_value(rows[field][0]))) + sum(len(WORD.findall(row)) for row in rows[field][1:])
    return ("pass" if count <= most else "fail"), f"{name}'s {field} has {count} words, and the most allowed is {most}"


def ends_with_one_question(bundle, file=None):
    text, name = _text(bundle, file)
    if text is None:
        return "fail", f"{name} does not exist"
    read = lines(text, file is not None)
    # Each span leaves its line breaks, so line N of the prose is still line N of the text.
    prose = SPAN.sub(lambda m: "\n" * m.group(0).count("\n"), "\n".join(r if k == "prose" else "" for k, r in read))
    asked = QUESTION.findall(prose)
    filled = [number for number, (kind, row) in enumerate(read) if row.strip()]
    end = prose.split("\n")[filled[-1]].rstrip().rstrip(CLOSERS) if filled and read[filled[-1]][0] == "prose" else ""
    last = end.endswith("?")
    if len(asked) == 1 and last:
        return "pass", f"{name} ends with its one question"
    return "fail", f"{name} holds {len(asked)} questions, and {'ends' if last else 'does not end'} with one"


def _runs(text, run):
    """Every run of `run` consecutive words of `text`, without case, as tuples, in order."""
    words = [w.lower() for w in WORD.findall(text)]
    return [tuple(words[i:i + run]) for i in range(len(words) - run + 1)]


def shares_words(bundle, source, run, shared, file=None):
    text, name = _text(bundle, file)
    original = bundle.text(source)
    if text is None or original is None:
        return "fail", f"{name if text is None else source} does not exist"
    runs = set(_runs(original, run))
    common = next((words for words in _runs(text, run) if words in runs), None)
    if common:
        return ("pass" if shared else "fail"), f"{name} shares {run} words with {source}: {' '.join(common)[:200]}"
    return ("fail" if shared else "pass"), f"{name} shares no run of {run} words with {source}"


def _strings(value):
    """The keys and strings of a decoded JSON value, in order."""
    if isinstance(value, dict):
        return [part for key, item in value.items() for part in [key, *_strings(item)]]
    if isinstance(value, list):
        return [part for item in value for part in _strings(item)]
    return [value] if isinstance(value, str) else []


def _words(bundle, path):
    """The text of the file at `path` as a reader sees it: a `.json` file that parses as its decoded keys and
    strings, so an escape such as `\\n` never joins or splits words; any other file as written."""
    text = bundle.text(path)
    if path.endswith(".json"):
        try:
            return "\n".join(_strings(json.loads(text.lstrip("\ufeff"))))
        except ValueError:
            pass
    return text


def no_shared_words(bundle, source, run, written):
    original = bundle.text(source)
    if original is None:
        return "fail", f"{source} does not exist"
    runs = set(_runs(_words(bundle, source), run))
    touched = sorted(path for path in bundle.changes if path != source and matches(path, written)
                     and path in bundle.files)
    other = [path for path in touched if bundle.text(path) is None and bundle.files[path] != "dir"]
    if other:  # only files and folders are read or allowed: a link could carry the source unread
        return "fail", f"the run wrote entries in {written} that are neither files nor folders: {', '.join(other[:20])}"
    read = [path for path in touched if bundle.text(path) is not None]
    for path in read:
        common = next((words for words in _runs(_words(bundle, path), run) if words in runs), None)
        if common:
            return "fail", f"{path} shares {run} words with {source}: {' '.join(common)[:200]}"
    return "pass", f"none of the {len(read)} files the run wrote in {written} shares a run of {run} words with {source}"


def _section(read, heading):
    """The (kind, row) lines under the prose heading `heading`, to the next prose heading of its level or above, or
    None when no prose heading is `heading`."""
    found, level = None, None
    for kind, row in read:
        title = HEADING.fullmatch(row) if kind == "prose" else None
        if found is not None and title and len(title.group(1)) <= level:
            break
        if found is not None:
            found.append((kind, row))
        elif title and (title.group(2) or "") == heading:
            found, level = [], len(title.group(1))
    return found


def line_counts(bundle, section, file=None):
    text, name = _text(bundle, file)
    if text is None:
        return "fail", f"{name} does not exist"
    rows = _section(lines(text, file is not None), section)
    if rows is None:
        return "fail", f"{name} has no heading {section!r}"
    other = [row for kind, row in rows if row.strip() and not (kind == "prose" and ENTRY.fullmatch(row))]
    listed = [ENTRY.fullmatch(row).groups() for kind, row in rows if row.strip() and kind == "prose"
              and ENTRY.fullmatch(row)]
    if other or not listed:
        return "fail", (f"{name}'s {section!r} lists {len(listed)} files, and holds lines that are not "
                        f"- `path` (N lines) or - `path` (deleted): {other[:5]}")
    wrong = []
    for path, count, deleted in listed:
        held = bundle.text(path) if is_path(path) else None
        true = None if held is None else held.count("\n")
        if not is_path(path):  # a path spelled any other way, such as ./src/app.py, names no world file
            wrong.append(f"{path} is not a world path")
        elif deleted and path in bundle.files:
            wrong.append(f"{path} is listed deleted but is there")
        elif not deleted and true is None:
            wrong.append(f"{path} is not a file")
        elif not deleted and true != int(count):
            wrong.append(f"{path} has {true} lines, not {count}")
    if wrong:
        return "fail", f"{name} lists {len(listed)} files, and " + "; ".join(wrong[:20])
    return "pass", f"{name} lists {len(listed)} files, each with its true line count or absent when deleted"


def line_references(bundle, file=None):
    text, name = _text(bundle, file)
    if text is None:
        return "fail", f"{name} does not exist"
    own = [row for row in _prose(text, file is not None) if not QUOTE.match(row)]
    spans = [m.group(0).strip("`").strip() for m in SPAN.finditer("\n".join(own))]
    entries = set(bundle.files) | {p for p, c in bundle.changes.items() if c["before"] is not None}
    world = {p.split("/")[0] for p in entries} | {p.split("/")[-1] for p in entries}
    found = [m.groups() for span in spans for m in [REFERENCE.fullmatch(span)]
             if m and {m.group(1).split("/")[0], m.group(1).split("/")[-1]} & world]
    broken = []
    for path, first, last in found:
        held = bundle.text(path) if is_path(path) else None  # ./src/app.py or src/../app.py is no world path
        if held is None:
            broken.append(f"{path} is not a file after the run")
            continue
        count = held.count("\n") + (not held.endswith("\n") and held != "")
        if not 1 <= int(first) <= int(last or first) <= count:
            broken.append(f"{path}:{first}{'-' + last if last else ''} is outside its {count} lines")
    if broken:
        return "fail", f"{name} holds broken file:line references: " + "; ".join(broken[:20])
    return "pass", f"{name} holds {len(found)} file:line references, each to lines that exist"


def is_text(value):
    return isinstance(value, str) and bool(value.strip())


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
    "no_shared_words": Check(no_shared_words, {"source": is_path, "run": is_count, "written": is_globs},
                             about="no file the run wrote in these globs shares a run of words with a source file"),
    "field_words": Check(field_words, {"field": is_text, "most": is_count, **FILE}, optional=("file",),
                         about="a frontmatter field holds at most this many words"),
    "line_counts": Check(line_counts, {"section": is_text, **FILE}, optional=("file",),
                         about="each file the text lists has the line count it gives, or is absent when deleted"),
    "line_references": Check(line_references, dict(FILE), optional=("file",),
                             about="every file:line reference in the text points at lines that exist"),
}
