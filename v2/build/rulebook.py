"""Read a rulebook layer folder, the roles file and skill frontmatter into plain data.

Standard library only. One rule governs the whole module: every line, and every value inside a line, must match a
shape listed here (HW-AG-09). Anything else raises RulebookError naming the file and line, so nothing is skipped or
guessed. The formats are those of docs/design/03-standards.md (rule parts, IDs, retired rules), v2/rules/README.md
(Review by) and v2/roles.md (roles and jobs tables).
"""

import re
from datetime import date
from dataclasses import dataclass, field
from pathlib import Path

EVERY_ROLE = "every role"
KINDS = ("principle", "floor", "idiom", "choice")
STATUSES = ("active", "inferred", "retired")
CLASSES = ("deep", "standard", "fast")
CHANGES = ("Overrides", "Binds", "Tightens")
RULE_REQUIRED = ("Kind", "Status", "Review by", "Applies to", "Rule", "Why", "Check", "Good", "Bad", "Eval", "Source")
DP_REQUIRED = ("Status", "Review by", "Question", "Options", "Default", "Why", "Applies to", "Source")
RULE_ALLOWED = RULE_REQUIRED + ("Replaced by", "Tool", "Exceptions") + CHANGES
DP_ALLOWED = DP_REQUIRED + ("Replaced by",)

NAME = r"[A-Z][A-Z0-9]*"
RULE_ID = re.compile(rf"{NAME}(?:-{NAME})+-[0-9]{{2,}}")
DP_ID = re.compile(rf"{NAME}(?:-{NAME})*-DP-[A-Z0-9]+(?:-[A-Z0-9]+)*")
ROLE = re.compile(r"[a-z]+(?: [a-z]+)*")
SKILL = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
PROSE = re.compile(r"[A-Za-z0-9(\[`].*")
FENCE = re.compile(r"`{3,}")
OPTION = re.compile(r"- `[a-z0-9-]+`: \S.*")
HEADING = re.compile(r"### (\S+) · (\S.*)")
PART = re.compile(r"- \*\*([A-Za-z ]+):\*\*(?: (\S.*))?")
AREA_TITLE = re.compile(rf"# ({NAME}(?:-{NAME})*) · \S.*")
RETIRED_TITLE = re.compile(r"# Retired rules · \S.*")
RETIRED_FILE = re.compile(r"retired(?:-[a-z0-9]+)?\.md")
NOT_RULE_FILES = ("index.md", "README.md")


class RulebookError(Exception):
    """A line or value with no allowed shape, or a missing part."""


@dataclass
class Rule:
    id: str
    title: str
    file: str
    line: int
    parts: dict = field(default_factory=dict)  # part name -> list of lines, verbatim, 2-space indent removed

    @property
    def is_decision_point(self):
        return DP_ID.fullmatch(self.id) is not None

    @property
    def kind(self):
        return "decision point" if self.is_decision_point else self.text("Kind")

    @property
    def status(self):
        return self.text("Status")

    @property
    def area(self):
        """The area part of the ID (HW-RULE-03): TEST for CORE-TEST-03, DP for every decision point."""
        return "DP" if self.is_decision_point else self.id.split("-")[-2]

    @property
    def applies_to(self):
        return split_list(self.text("Applies to"))

    @property
    def changes(self):
        """The ID this rule overrides, binds or tightens, or None."""
        return next((self.text(name) for name in CHANGES if name in self.parts), None)

    def text(self, part):
        """The part's lines joined with line breaks, exactly as the rulebook writes them."""
        return "\n".join(self.parts[part])


@dataclass
class Layer:
    folder: str
    rules: dict = field(default_factory=dict)  # ID -> Rule, active, inferred and retired alike


def split_list(value):
    """Split a comma-and-space list such as an Applies to value."""
    return value.split(", ") if value else []


def is_date(value):
    try:
        return date.fromisoformat(value) is not None
    except ValueError:
        return False


def fail(path, number, message):
    raise RulebookError(f"{path}:{number}: {message}")


def read_lines(path):
    """The file's lines. LF line endings and a final newline are required."""
    with open(path, encoding="utf-8", newline="") as handle:
        text = handle.read()
    if "\r" in text:
        fail(path, 1, "file has a carriage return; use LF line endings")
    if not text.endswith("\n"):
        fail(path, text.count("\n") + 1, "file does not end with a newline")
    return text[:-1].split("\n")


def read_layer(folder):
    """Read every rule file of one layer folder. The index and README are not read (HW-RULE-08)."""
    folder = Path(folder)
    if not folder.is_dir():
        fail(folder, 0, "not a layer folder")
    layer = Layer(str(folder))
    for path in sorted(p for p in folder.glob("*.md") if p.name not in NOT_RULE_FILES):
        for rule in read_rule_file(path):
            if rule.id in layer.rules:
                other = layer.rules[rule.id]
                fail(path, rule.line, f"{rule.id} already defined at {other.file}:{other.line}")
            layer.rules[rule.id] = rule
    return layer


def read_rule_file(path):
    """Read one area file or retired rules file and return its rules in file order."""
    path = Path(path)
    lines = read_lines(path)
    retired_file = RETIRED_FILE.fullmatch(path.name) is not None
    title = (RETIRED_TITLE if retired_file else AREA_TITLE).fullmatch(lines[0])
    if title is None:
        fail(path, 1, "first line is not the file title")
    prefix = None if retired_file else title.group(1)
    rules, rule, part, fence = [], None, None, ""
    for number, line in enumerate(lines[1:], start=2):
        heading = None if fence else HEADING.fullmatch(line)
        if heading:
            rule, part = start_rule(path, number, heading, prefix), None
            rules.append(rule)
        elif rule is None:
            if line and not PROSE.fullmatch(line):
                fail(path, number, f"line outside a rule is not prose: {line!r}")
        elif not fence and HEADING.fullmatch(line.lstrip()):
            fail(path, number, f"rule heading must not be indented: {line!r}")
        elif line.startswith("  ") and part is not None:
            text, run = line[2:].strip(), FENCE.match(line[2:].lstrip())
            if run and not fence:
                fence = run.group()  # a code block closes only on a line of at least as many backticks
            elif fence and text.startswith(fence) and text.strip("`") == "":
                fence = ""
            rule.parts[part].append(line[2:])
        elif line == "":
            if fence:
                rule.parts[part].append("")
            else:
                part = None
        elif fence:
            fail(path, number, "code block is not closed before the next part")
        else:
            part = add_part(path, number, rule, line)
    if fence:
        fail(path, len(lines), "code block is never closed")
    for index, rule in enumerate(rules):
        if rule.id in (other.id for other in rules[:index]):
            fail(path, rule.line, f"{rule.id} already defined in this file")
        check_rule(path, rule, retired_file)
    return rules


def start_rule(path, number, heading, prefix):
    rule_id, title = heading.groups()
    is_point = DP_ID.fullmatch(rule_id)
    is_rule = not is_point and RULE_ID.fullmatch(rule_id)
    if not (is_rule or is_point):
        fail(path, number, f"{rule_id!r} is not a rule or decision point ID")
    if prefix is not None:
        expected = re.fullmatch(rf"{prefix}-[0-9]{{2,}}", rule_id) if is_rule else (
            prefix.endswith("-DP") and rule_id.startswith(prefix + "-"))
        if not expected:
            fail(path, number, f"{rule_id} does not belong in a file titled {prefix}")
    return Rule(rule_id, title, str(path), number)


def add_part(path, number, rule, line):
    found = PART.fullmatch(line)
    if found is None:
        fail(path, number, f"line has no known shape inside {rule.id}: {line!r}")
    name = found.group(1)
    if name not in (DP_ALLOWED if rule.is_decision_point else RULE_ALLOWED):
        fail(path, number, f"part {name!r} is not allowed in {rule.id}")
    if name in rule.parts:
        fail(path, number, f"part {name!r} appears twice in {rule.id}")
    rule.parts[name] = [found.group(2) or ""]
    return name


def check_rule(path, rule, retired_file):
    required = DP_REQUIRED if rule.is_decision_point else RULE_REQUIRED
    missing = [name for name in required if name not in rule.parts]
    if missing:
        fail(path, rule.line, f"{rule.id} is missing {', '.join(missing)}")
    for name in rule.parts:
        check_value(path, rule, name)
    retired = rule.text("Status") == "retired"
    if retired != ("Replaced by" in rule.parts):
        fail(path, rule.line, f"{rule.id}: Replaced by is required exactly when the status is retired")
    if retired != retired_file:
        fail(path, rule.line, f"{rule.id}: retired rules live in retired files and only there (HW-RULE-07)")
    if sum(name in rule.parts for name in CHANGES) > 1:
        fail(path, rule.line, f"{rule.id} names more than one of {', '.join(CHANGES)} (HW-RULE-05)")


def check_value(path, rule, name):
    """Each part's value must have its allowed shape. Text parts must not be empty."""
    value, lines = rule.text(name), rule.parts[name]
    if name in ("Options", "Source") and lines[0] == "":
        shape = OPTION if name == "Options" else re.compile(r"- \S.*")
        ok = len(lines) > 1 and all(shape.fullmatch(item) or item.startswith("  ") for item in lines[1:])
        ok = ok and not lines[1].startswith("  ")
    elif name == "Options":
        ok = False
    elif name == "Kind":
        ok = value in KINDS
    elif name == "Status":
        ok = value in STATUSES
    elif name == "Review by":
        ok = DATE.fullmatch(value) is not None and is_date(value)
    elif name == "Applies to":
        names = split_list(value)
        ok = bool(names) and len(set(names)) == len(names) and all(ROLE.fullmatch(n) for n in names)
    elif name == "Replaced by":
        ids = split_list(value)
        ok = value == "no replacement" or ids and all(RULE_ID.fullmatch(i) or DP_ID.fullmatch(i) for i in ids)
    elif name in CHANGES:
        ok = RULE_ID.fullmatch(value) is not None or DP_ID.fullmatch(value) is not None
    else:
        ok = value.strip() != ""
    if not ok:
        fail(path, rule.line, f"{rule.id}: {name} has no allowed value: {value!r}")


ROLES_COLUMNS = ("Role", "Group", "Purpose", "Produces", "Never does", "Model class", "Independent")
JOBS_COLUMNS = ("Job", "Roles", "Skills in order", "`rest` skill")


def read_roles(path):
    """Read v2/roles.md: the Roles table and the Jobs table, which may have no rows."""
    path = Path(path)
    lines = read_lines(path)
    roles = read_table(path, lines, "## Roles", ROLES_COLUMNS)
    jobs = read_table(path, lines, "## Jobs", JOBS_COLUMNS)
    classes = {f"{a} or {b}" for a in CLASSES for b in CLASSES if a != b} | set(CLASSES)
    for number, row in roles:
        ok = (ROLE.fullmatch(row["Role"]) and row["Role"] != EVERY_ROLE and ROLE.fullmatch(row["Group"])
              and row["Purpose"] and row["Produces"] and row["Model class"] in classes
              and row["Independent"] in ("yes", "no"))
        if not ok:
            fail(path, number, f"role row has a cell with no allowed value: {row}")
    for number, row in jobs:
        row["Roles"], row["Skills in order"] = split_list(row["Roles"]), split_list(row["Skills in order"])
        ok = (SKILL.fullmatch(row["Job"]) and row["Roles"] and row["Skills in order"]
              and all(ROLE.fullmatch(r) and r != EVERY_ROLE for r in row["Roles"])
              and all(SKILL.fullmatch(s) for s in row["Skills in order"])
              and row["`rest` skill"] in row["Skills in order"])
        if not ok:
            fail(path, number, f"job row has a cell with no allowed value: {row}")
    return {"roles": unique(path, roles, "Role"), "jobs": unique(path, jobs, "Job")}


def unique(path, rows, column):
    table = {}
    for number, row in rows:
        if row[column] in table:
            fail(path, number, f"{row[column]!r} is listed twice")
        table[row[column]] = row
    return table


def read_table(path, lines, heading, columns):
    """(line number, row) pairs under one heading. Prose may come before the table; after it, only blank lines."""
    if lines.count(heading) != 1:
        fail(path, 1, f"expected exactly one {heading!r} heading")
    start = lines.index(heading) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("#")), len(lines))
    header = "| " + " | ".join(columns) + " |"
    if lines[start:end].count(header) != 1:
        fail(path, start, f"expected one table with the header {header} under {heading!r}")
    first = lines.index(header, start)
    rule_line = lines[first + 1] if first + 1 < end else ""
    if any(line.startswith("|") for line in lines[start:first]) or rule_line != "|" + "---|" * len(columns):
        fail(path, first + 1, f"table under {heading!r} is not a header, a rule line and rows")
    rows, number = [], first + 2
    while number < end and lines[number].startswith("|"):
        line = lines[number]
        cells = [cell.strip() for cell in line[1:-1].split("|")] if line.endswith("|") else []
        if len(cells) != len(columns):
            fail(path, number + 1, f"row needs {len(columns)} cells between '|' signs")
        rows.append((number + 1, dict(zip(columns, cells))))
        number += 1
    for index in range(number, end):
        if lines[index] != "":
            fail(path, index + 1, f"only blank lines may follow the table under {heading!r}")
    return rows


FRONTMATTER_KEYS = ("name", "description", "license", "compatibility")
TOP_LINE = re.compile(r"([a-z][a-z-]*): (\S.*)")
# Every value character is YAML-printable and not a tab or line break. A plain value starts with a letter, so it is
# never a number, date or special float, and is not a YAML 1.1 bool or null word, so every reader sees a string.
PRINTABLE = "[\x20-\x7e\xa0-\u2027\u202a-\ud7ff\ue000-\ufefe\uff00-\ufffd\U00010000-\U0010ffff]"
WORDS = r"(?:[yYnN]|[yY]es|YES|[nN]o|NO|[tT]rue|TRUE|[fF]alse|FALSE|[oO]n|ON|[oO]ff|OFF|[nN]ull|NULL)"
META_LINE = re.compile(rf"  (?!{WORDS}:)([a-z][a-z0-9-]*): (\S.*)")  # a key is a YAML string too
PLAIN = re.compile(rf"(?!{WORDS}$)[A-Za-z](?:(?!: | #){PRINTABLE})*(?<![ :])")
QUOTED = re.compile(rf"\"((?:(?![\"\\]){PRINTABLE})*)\"|'((?:(?!'){PRINTABLE})*)'")


def read_frontmatter(path):
    """The frontmatter of a SKILL.tmpl.md or SKILL.md: top-level strings and a `metadata` map of strings.

    Returns the data and the 0-based index of the first body line. A value is a plain string that starts with a
    letter (PLAIN) or a quoted string without escapes. Any other shape fails, so every host reads the same string.
    """
    path = Path(path)
    lines = read_lines(path)
    if lines[0] != "---" or "---" not in lines[1:]:
        fail(path, 1, "file does not start with a frontmatter block")
    end = lines.index("---", 1)
    data, target = {}, None
    for number in range(1, end):
        line = lines[number]
        meta = META_LINE.fullmatch(line)
        top = TOP_LINE.fullmatch(line)
        if line == "metadata:" and "metadata" not in data:
            target = data["metadata"] = {}
        elif meta and target is not None:
            store(path, number + 1, target, meta.groups())
        elif top and top.group(1) in FRONTMATTER_KEYS:
            target = None
            store(path, number + 1, data, top.groups())
        else:
            fail(path, number + 1, f"frontmatter line has no allowed shape: {line!r}")
    return data, end + 1


def store(path, number, target, pair):
    key, value = pair
    quoted = QUOTED.fullmatch(value)
    if key in target:
        fail(path, number, f"{key!r} appears twice")
    if quoted:
        value = quoted.group(1) if quoted.group(1) is not None else quoted.group(2)
    elif PLAIN.fullmatch(value) is None:
        fail(path, number, f"value of {key!r} has no allowed shape: quote it, without escapes")
    target[key] = value
