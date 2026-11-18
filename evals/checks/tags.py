"""Checks of the rule tags in a skill template a run wrote. The kit keeps its own reader, written apart from the
build's (`v2/build/tags.py`) and the release check's, so a fault in one cannot pass the others; all three are tested
against the same bad lines, `v2/build/tests/golden/tag-faults.md`.

One rule, an allow list of line shapes: a rule tag, `{{rule:ID}}`, stands only on a `Rules:` line, which after any
indentation by spaces is `Rules: ` and then one or more tags separated by ", ", with nothing else. Every other line
of the body holds no tag, nothing that starts like one (`{` then `rule` as a word, in any case and with any spaces
between), and no rule ID outside a tag. The form itself, `{{rule:<ID>}}`, holds no ID and may stand anywhere but a
`Rules:` line. An ID inside a word, a file name or a path is not a citation. The frontmatter (the leading `---`
block) holds no tag and no rule ID.

- `rule_tags`: the template at `file` follows that rule; it tags at least one rule; every tagged ID is listed in the
  world file `index` as it was before the run (an index the run changed fails, so a run cannot list its own IDs);
  and for each group of IDs in `require`, at least one of the group is tagged. An ID is a whole match of `pattern`.
"""

import re

from cases import is_path
from checks import Check, is_pattern

PLACEHOLDER = "{{rule:<ID>}}"
STARTS_A_TAG = re.compile(r"\{\s*rule\b", re.IGNORECASE)


def _id(pattern):
    """An ID as a citation: no letter, digit, `_`, `-`, `/` or `.` before it, and no letter, digit, `_`, `-` or `/`
    after it, nor a `.` followed by a letter or digit (a file extension)."""
    return rf"(?<![\w/.-])(?:{pattern})(?![\w/-]|\.\w)"


def _body(lines):
    """The index of the first body line: after the closing `---` of a leading frontmatter block, else 0."""
    if lines and lines[0].strip() == "---":
        for number in range(1, len(lines)):
            if lines[number].strip() == "---":
                return number + 1
    return 0


def rule_tags(bundle, file, index, pattern, require=()):
    text, listed = bundle.text(file), bundle.text(index)
    if text is None or listed is None:
        return "fail", f"{file if text is None else index} does not exist"
    if index in bundle.changes:
        return "fail", f"the run changed {index}, so it cannot vouch for the IDs tagged"
    cited = re.compile(_id(pattern))
    tag = re.compile(rf"\{{\{{rule:({pattern})\}}\}}")
    item = rf"\{{\{{rule:(?:{pattern})\}}\}}"
    rules_line = re.compile(rf" *Rules: {item}(?:, {item})*")
    known = {found.group(0) for found in cited.finditer(listed)}
    lines = text.split("\n")
    start = _body(lines)
    for number, line in enumerate(lines[:start], start=1):
        if STARTS_A_TAG.search(line) or cited.search(line):
            return "fail", f"{file}:{number}: the frontmatter holds no rule tag and no rule ID: {line[:120]!r}"
    tagged = []
    for number, line in enumerate(lines[start:], start=start + 1):
        if line.lstrip(" ").startswith("Rules:"):
            if not rules_line.fullmatch(line):
                return "fail", (f"{file}:{number}: a `Rules:` line holds only rule tags, with real IDs, "
                                f"separated by \", \": {line[:120]!r}")
            ids = [found.group(1) for found in tag.finditer(line)]
            unlisted = [rule_id for rule_id in ids if rule_id not in known]
            if unlisted:
                return "fail", f"{file}:{number}: tags {unlisted[0]}, which {index} does not list: {line[:120]!r}"
            tagged += ids
            continue
        rest = line.replace(PLACEHOLDER, "")
        if tag.search(line) or STARTS_A_TAG.search(rest):
            return "fail", f"{file}:{number}: a rule tag stands only on a `Rules:` line: {line[:120]!r}"
        bare = cited.search(rest)
        if bare:
            return "fail", f"{file}:{number}: cites {bare.group()} outside a tag: {line[:120]!r}"
    missing = [group for group in require if not set(group) & set(tagged)]
    if not tagged or missing:
        return "fail", (f"{file} tags {len(set(tagged))} IDs; groups with none tagged: "
                        f"{'; '.join('/'.join(group) for group in missing) or '-'}")
    return "pass", f"{file} tags {len(set(tagged))} IDs, each listed in {index}: {', '.join(sorted(set(tagged))[:20])}"


def is_groups(value):
    """Whether `value` is a list of groups, each a non-empty list of non-empty IDs."""
    return isinstance(value, list) and all(
        isinstance(group, list) and group and all(isinstance(i, str) and i for i in group) for group in value)


CHECKS = {
    "rule_tags": Check(rule_tags, {"file": is_path, "index": is_path, "pattern": is_pattern, "require": is_groups},
                       optional=("require",),
                       about="rule tags stand only on Rules: lines, no ID stands bare, and every tag is indexed"),
}
