"""Read the rule tags of a skill template and expand them into release text.

Standard library only, build only: this module is not shipped with a skill (build.SHIPPED). One rule governs it
(HW-AG-09): a rule tag, `{{rule:ID}}`, stands only on a `Rules:` line, and every line that starts with `Rules:` has
one allowed shape. A `Rules:` line is one line that, after any indentation by spaces, is `Rules: ` and then one or
more tags separated by ", ", with nothing else. It never wraps: a wrapped line leaves a tag outside a `Rules:` line,
or a line that ends with a comma, and both fail. The tag `{{rule:<ID>}}` holds no rule ID; it shows the form
itself, so the build leaves it as it is, on a `Rules:` line or anywhere else. Any other `{` followed by `rule` as a
word, in any case and with any spaces between, is a mistyped tag and fails; other braces, such as JSON, are text.

The build writes each tag as "ID (title)". A rule ID anywhere else in the body, outside a tag, fails: a rule is
cited only by a tag (CORE-TEMPLATE-05). An ID inside a word, a file name or a path is not a citation. The
frontmatter cites nothing; it may hold no tag.

check_rules.py checks the release with its own reader, so a fault here cannot hide itself.
"""

import re

import rulebook

ID = rf"(?:{rulebook.DP_ID.pattern}|{rulebook.RULE_ID.pattern})"
# An ID inside a word, a file name or a path is not a citation: no letter, digit, "-", "/" or "." before it, and no
# letter, digit, "-" or "/" after it, nor a "." followed by a letter or digit (a file extension).
CITATION = re.compile(rf"(?<![\w/.-]){ID}(?![\w/-]|\.\w)")
PLACEHOLDER = "{{rule:<ID>}}"
TAG = re.compile(rf"\{{\{{rule:({ID})\}}\}}")
ITEM = rf"(?:\{{\{{rule:{ID}\}}\}}|{re.escape(PLACEHOLDER)})"
RULES_LINE = re.compile(rf" *Rules: {ITEM}(?:, {ITEM})*")
MISTYPED = re.compile(r"\{\s*rule\b", re.IGNORECASE)  # the start of a tag; left over, it has no allowed shape


class TagError(rulebook.RulebookError):
    """A rule tag or a `Rules:` line with no allowed shape, or a tag for a rule the layer does not hold."""


def is_rules_line(line):
    return line.lstrip(" ").startswith("Rules:")


def ids(text):
    """Every rule ID the text cites, in a tag or bare."""
    return set(CITATION.findall(text))


def check_frontmatter(lines, where):
    """The frontmatter holds no tag: the build writes it out as it is, so a tag there would reach the release."""
    for number, line in enumerate(lines, start=1):
        if MISTYPED.search(line):
            raise TagError(f"{where}:{number}: the frontmatter holds no rule tag: {line!r}")


def expand(text, titles, where, first=1):
    """The text with each tag written as "ID (title)", line for line. titles maps each ID the layer holds to its
    title; first is the file line number of the text's first line. Fails, naming where and the line, on a tag or
    `Rules:` line with no allowed shape, a rule ID outside a tag, or an unknown ID."""
    def title(found):
        rule_id = found.group(1)
        if rule_id not in titles:
            raise TagError(f"{where}:{number}: cites {rule_id}, which is not in the CORE rulebook")
        return f"{rule_id} ({titles[rule_id]})"

    lines = text.split("\n")
    for index, line in enumerate(lines):
        number = first + index
        if is_rules_line(line):
            if not RULES_LINE.fullmatch(line):
                raise TagError(f"{where}:{number}: a `Rules:` line holds only rule tags such as {PLACEHOLDER}, "
                               f"separated by \", \", on one line: {line!r}")
            lines[index] = TAG.sub(title, line)
            continue
        if TAG.search(line):
            raise TagError(f"{where}:{number}: a rule tag stands only on a `Rules:` line: {line!r}")
        if MISTYPED.search(line.replace(PLACEHOLDER, "")):
            raise TagError(f"{where}:{number}: a rule tag is written {PLACEHOLDER}, with a rule ID: {line!r}")
        bare = CITATION.search(line)
        if bare:
            raise TagError(f"{where}:{number}: cites {bare.group()} outside a tag; write it as "
                           f"{{{{rule:{bare.group()}}}}} on a `Rules:` line: {line!r}")
    return "\n".join(lines)
