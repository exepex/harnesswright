"""Read a rulebook layer folder, the roles file and skill frontmatter into plain data.

Standard library only. Every line must have a shape this module knows. Any other line raises RulebookError,
naming the file and line, so nothing is ever skipped silently. The formats are those of docs/design/03-standards.md
(rule parts, IDs, retired rules), v2/rules/README.md (Review by) and v2/roles.md (roles and jobs tables).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

RULE_REQUIRED = ("Kind", "Status", "Review by", "Applies to", "Rule", "Why", "Check", "Good", "Bad", "Eval", "Source")
DP_REQUIRED = ("Status", "Review by", "Question", "Options", "Default", "Why", "Applies to", "Source")
OPTIONAL = ("Replaced by", "Overrides", "Binds", "Tightens", "Tool", "Exceptions")
CHANGES = ("Overrides", "Binds", "Tightens")
KINDS = ("principle", "floor", "idiom", "choice")
STATUSES = ("active", "inferred", "retired")
EVERY_ROLE = "every role"

RULE_ID = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-[0-9]{2,}")
DP_ID = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-DP-[A-Z0-9]+(?:-[A-Z0-9]+)*")
HEADING = re.compile(r"### (\S+) · (\S.*)")
PART = re.compile(r"- \*\*([A-Za-z ]+):\*\*(?: (.*))?")
AREA_TITLE = re.compile(r"# ([A-Z][A-Z0-9-]*) · \S.*")
RETIRED_TITLE = re.compile(r"# Retired rules · \S.*")
RETIRED_FILE = re.compile(r"retired(?:-[a-z0-9]+)?\.md")
NOT_RULE_FILES = ("index.md", "README.md")


class RulebookError(Exception):
    """A rulebook, roles file or frontmatter line this module does not recognise, or a missing part."""


@dataclass
class Rule:
    id: str
    title: str
    file: str
    line: int
    parts: dict = field(default_factory=dict)  # part name -> list of lines, verbatim, 2-space indent removed

    @property
    def is_decision_point(self):
        return "-DP-" in self.id

    @property
    def kind(self):
        return "decision point" if self.is_decision_point else self.text("Kind")

    @property
    def status(self):
        return self.text("Status")

    @property
    def area(self):
        return "DP" if self.is_decision_point else self.id.split("-")[-2]

    @property
    def applies_to(self):
        return split_list(self.text("Applies to"))

    @property
    def replaced_by(self):
        return split_list(self.text("Replaced by")) if "Replaced by" in self.parts else []

    @property
    def changes(self):
        """(relation, ID) for an Overrides, Binds or Tightens part, else None."""
        for name in CHANGES:
            if name in self.parts:
                return name, self.text(name)
        return None

    def text(self, part):
        """The part's lines joined with line breaks, exactly as the rulebook writes them."""
        return "\n".join(self.parts[part])


@dataclass
class Layer:
    folder: str
    rules: dict = field(default_factory=dict)  # ID -> Rule, active, inferred and retired alike


def split_list(value):
    """Split a comma-separated list such as an Applies to value. An empty value gives an empty list."""
    return [item.strip() for item in value.split(",")] if value.strip() else []


def fail(path, number, message):
    raise RulebookError(f"{path}:{number}: {message}")


def read_layer(folder):
    """Read every rule file of one layer folder. The index and README are not read (HW-RULE-08)."""
    folder = Path(folder)
    layer = Layer(str(folder))
    files = sorted(p for p in folder.glob("*.md") if p.name not in NOT_RULE_FILES)
    for path in files:
        for rule in read_rule_file(path):
            if rule.id in layer.rules:
                other = layer.rules[rule.id]
                fail(path, rule.line, f"{rule.id} already defined at {other.file}:{other.line}")
            layer.rules[rule.id] = rule
    return layer


def read_rule_file(path):
    """Read one area file or retired rules file and return its rules in file order."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").split("\n")
    if lines[-1] != "":
        fail(path, len(lines), "file does not end with a newline")
    lines = lines[:-1]
    retired_file = RETIRED_FILE.fullmatch(path.name) is not None
    title = RETIRED_TITLE if retired_file else AREA_TITLE
    match = title.fullmatch(lines[0]) if lines else None
    if match is None:
        fail(path, 1, "first line is not the file title")
    prefix = None if retired_file else match.group(1)
    rules = []
    rule = part = None
    fenced = False
    for number, line in enumerate(lines, start=1):
        heading = HEADING.fullmatch(line)
        if heading and not fenced:
            rule = start_rule(path, number, heading, prefix)
            rules.append(rule)
            part = None
            continue
        if rule is None:
            if number > 1 and (line.startswith("#") or line.startswith("- **")):
                fail(path, number, f"heading or part outside a rule: {line!r}")
            continue  # the file's title and opening prose
        if line.startswith("  ") and part is not None:
            text = line[2:]
            if text.lstrip().startswith("```"):
                fenced = not fenced
            rule.parts[part].append(text)
            continue
        if line == "" and fenced:
            rule.parts[part].append("")
            continue
        if line == "":
            part = None
            continue
        found = PART.fullmatch(line)
        if found is None:
            fail(path, number, f"line has no known shape inside {rule.id}: {line!r}")
        part = found.group(1)
        if part not in RULE_REQUIRED + DP_REQUIRED + OPTIONAL:
            fail(path, number, f"unknown part {part!r} in {rule.id}")
        if part in rule.parts:
            fail(path, number, f"part {part!r} appears twice in {rule.id}")
        rule.parts[part] = [found.group(2) or ""]
    if fenced:
        fail(path, len(lines), "code block is never closed")
    for rule in rules:
        check_parts(path, rule, retired_file)
    return rules


def start_rule(path, number, heading, prefix):
    rule_id, title = heading.group(1), heading.group(2)
    if not (RULE_ID.fullmatch(rule_id) or DP_ID.fullmatch(rule_id)):
        fail(path, number, f"{rule_id!r} is not a rule or decision point ID")
    if prefix is not None and not rule_id.startswith(prefix + "-"):
        fail(path, number, f"{rule_id} does not belong in a file titled {prefix}")
    return Rule(rule_id, title, str(path), number)


def check_parts(path, rule, retired_file):
    required = DP_REQUIRED if rule.is_decision_point else RULE_REQUIRED
    missing = [name for name in required if name not in rule.parts]
    if missing:
        fail(path, rule.line, f"{rule.id} is missing {', '.join(missing)}")
    if rule.is_decision_point and "Kind" in rule.parts:
        fail(path, rule.line, f"decision point {rule.id} has a Kind")
    if not rule.is_decision_point and rule.kind not in KINDS:
        fail(path, rule.line, f"{rule.id} has unknown Kind {rule.kind!r}")
    if rule.status not in STATUSES:
        fail(path, rule.line, f"{rule.id} has unknown Status {rule.status!r}")
    if (rule.status == "retired") != ("Replaced by" in rule.parts):
        fail(path, rule.line, f"{rule.id}: Replaced by is required exactly when the status is retired")
    if (rule.status == "retired") != retired_file:
        fail(path, rule.line, f"{rule.id}: retired rules live in retired files and only there (HW-RULE-07)")
    if sum(name in rule.parts for name in CHANGES) > 1:
        fail(path, rule.line, f"{rule.id} names more than one of {', '.join(CHANGES)} (HW-RULE-05)")


def read_roles(path):
    """Read v2/roles.md: the Roles table and the Jobs table, which may have no rows."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").split("\n")
    roles = read_table(path, lines, "## Roles",
                       ["Role", "Group", "Purpose", "Produces", "Never does", "Model class", "Independent"])
    jobs = read_table(path, lines, "## Jobs", ["Job", "Roles", "Skills in order", "`rest` skill"])
    names = [row["Role"] for row in roles]
    if EVERY_ROLE in names:
        fail(path, 1, f"{EVERY_ROLE!r} is reserved and is never a role")
    if len(set(names)) != len(names):
        fail(path, 1, "a role is listed twice")
    for row in jobs:
        row["Roles"] = split_list(row["Roles"])
        row["Skills in order"] = split_list(row["Skills in order"])
    return {"roles": {row["Role"]: row for row in roles}, "jobs": {row["Job"]: row for row in jobs}}


def read_table(path, lines, heading, columns):
    """The rows under one heading as dicts. The header must match `columns` exactly."""
    if lines.count(heading) != 1:
        fail(path, 1, f"expected exactly one {heading!r} heading")
    number = lines.index(heading) + 1
    while number < len(lines) and not lines[number].startswith("|"):
        if lines[number].startswith("#"):
            fail(path, number + 1, f"no table under {heading!r}")
        number += 1
    header = "| " + " | ".join(columns) + " |"
    rule = "|" + "---|" * len(columns)
    if lines[number:number + 2] != [header, rule]:
        fail(path, number + 1, f"table under {heading!r} does not have the header {header}")
    rows = []
    for index in range(number + 2, len(lines)):
        line = lines[index]
        if not line.startswith("|"):
            break
        if not line.endswith("|"):
            fail(path, index + 1, "table row does not end with '|'")
        cells = [cell.strip() for cell in line[1:-1].split("|")]
        if len(cells) != len(columns) or not cells[0]:
            fail(path, index + 1, f"row needs {len(columns)} cells and a first cell")
        rows.append(dict(zip(columns, cells)))
    return rows


FRONTMATTER_KEYS = ("name", "description", "license", "compatibility", "metadata")
TOP_LINE = re.compile(r"([a-z][a-z-]*): (\S.*)")
META_LINE = re.compile(r"  ([a-z][a-z-]*): (\S.*)")


def read_frontmatter(path):
    """The frontmatter of a SKILL.tmpl.md or SKILL.md: top-level string fields and a `metadata` map of strings."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").split("\n")
    if lines[0] != "---" or "---" not in lines[1:]:
        fail(path, 1, "file does not start with a frontmatter block")
    end = lines.index("---", 1)
    data = {}
    in_metadata = False
    for number in range(1, end):
        line = lines[number]
        if line == "metadata:" and "metadata" not in data:
            data["metadata"] = {}
            in_metadata = True
            continue
        meta = META_LINE.fullmatch(line)
        if meta and in_metadata:
            store(path, number + 1, data["metadata"], meta.group(1), meta.group(2))
            continue
        top = TOP_LINE.fullmatch(line)
        if top is None or top.group(1) not in FRONTMATTER_KEYS or top.group(1) == "metadata":
            fail(path, number + 1, f"frontmatter line has no allowed shape: {line!r}")
        in_metadata = False
        store(path, number + 1, data, top.group(1), top.group(2))
    return data, end + 1


def store(path, number, target, key, value):
    if key in target:
        fail(path, number, f"{key!r} appears twice")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    target[key] = value
