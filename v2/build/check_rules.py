"""Check the rulebook, the roles file, the templates, and the floors and areas each release skill copies.

Standard library only. It imports nothing from the build: it reads rule files, the roles file and frontmatter by
its own, simpler method, so a fault in the build's reader cannot hide itself (reviews/release-design/final-design.md
section 5; plan/b01-plan.md part d1). It collects every failure, prints each as "check failed: <where>: <what>" and
returns 1; with none it returns 0. One rule governs its readers: each line has an allowed shape, or it fails. Each
`check_*` method of Check covers one kind of failure: rule parts and roles, copy markers, templates and their
citations, jobs, release copies, bare IDs, rule tags and `Rules:` lines, job names given with --job, and the
version bump.

Run: python3 v2/build/check_rules.py [--root ROOT] [--release DIR] [--changed FILE] [--job NAME]...
"""

import argparse
import re
import sys
from pathlib import Path

EVERY_ROLE = "every role"
REST = "rest"
KINDS = ("principle", "floor", "idiom", "choice")
STATUSES = ("active", "inferred", "retired")
RULE_PARTS = ("Kind", "Status", "Review by", "Applies to", "Rule", "Why", "Check", "Good", "Bad", "Eval", "Source")
POINT_PARTS = ("Status", "Review by", "Question", "Options", "Default", "Why", "Applies to", "Source")
NOT_RULE_FILES = ("index.md", "README.md")
SEGMENT = r"[A-Z][A-Z0-9]*"
RULE_ID = rf"{SEGMENT}(?:-{SEGMENT})+-[0-9]{{2,}}"
POINT_ID = rf"{SEGMENT}(?:-{SEGMENT})*-DP(?:-[A-Z0-9]+)+"
# The same rule as the build: an ID inside a word, a file name or a path is not a citation.
CITED = re.compile(rf"(?<![\w/.-])({POINT_ID}|{RULE_ID})(?![\w/-]|\.\w)")
HEADING = re.compile(r"### (\S+) · (.+)")
PART = re.compile(r"- \*\*([A-Za-z ]+):\*\*(?: (.*))?")
BEGIN = re.compile(r"<!-- rule (\S+) -->")
END = re.compile(r"<!-- end (\S+) -->")
PROSE = re.compile(r"[A-Za-z0-9(\[`].*")  # a line of text outside a rule or table
FRONT = re.compile(r"(?:  )?[a-z][a-z0-9-]*: \S.*|metadata:")
MARKERS = ("<!-- rule ", "<!-- end ", "<!-- Generated from ")
SECTION = "## Rules for this skill"
# A rule tag, {{rule:ID}}, is template text: the build writes each one out as "ID (title)". A release shows only the
# form itself, {{rule:<ID>}}; any other "{" followed by the word "rule", in any case, is a tag the build did not
# write out. Other braces, such as JSON, are text.
PLACEHOLDER = "{{rule:<ID>}}"
TAG_LEFT = re.compile(r"\{\s*rule\b", re.IGNORECASE)
ITEM = re.compile(rf"({POINT_ID}|{RULE_ID}) \(")


class Rule:
    def __init__(self, rule_id, title, where):
        self.id, self.title, self.where, self.parts, self.twice = rule_id, title, where, {}, []

    @property
    def is_point(self):
        return re.fullmatch(POINT_ID, self.id) is not None

    def value(self, name):
        return self.parts.get(name, "").strip()

    @property
    def roles(self):
        return set(names(self.value("Applies to")))

    @property
    def area(self):
        return None if self.is_point else self.id.split("-")[-2]


def read_rules(path, root, fail):
    """Rules of one file. Each line must have one allowed shape, or it fails: the title first; prose and blank
    lines before the first rule; a '### ID · title' heading; a '- **Name:**' part inside a rule; a line indented
    by two spaces inside a part; a blank line."""
    rules, rule, part = [], None, None
    where = path.relative_to(root).as_posix()
    for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), start=1):
        heading, found = HEADING.fullmatch(line), PART.fullmatch(line)
        if heading:
            rule, part = Rule(*heading.groups(), f"{where}:{number}"), None
            rules.append(rule)
        elif rule is not None and found:
            part = found.group(1)
            if part in rule.parts:
                rule.twice.append(part)
            rule.parts[part] = found.group(2) or ""
        elif part is not None and (line.startswith("  ") or line == ""):
            rule.parts[part] += "\n" + line
        elif not (line == "" or (number == 1 and line.startswith("# ")) or (rule is None and PROSE.fullmatch(line))):
            fail(f"{where}:{number}", f"line has no allowed shape: {line!r}")
    return rules


def metadata(path, fail):
    """The name and the metadata keys of a frontmatter block, quotes removed. A line of another shape fails."""
    lines = path.read_text(encoding="utf-8").split("\n")
    end = lines.index("---", 1)
    found, seen = {}, set()
    for number, line in enumerate(lines[1:end], start=2):
        key, _, value = line.strip().partition(": ")
        if not FRONT.fullmatch(line) or line.split(":")[0] in seen:
            fail(f"{path.name}:{number}", f"frontmatter line has no allowed shape or repeats a key: {line!r}")
        elif line.startswith(("name: ", "  roles: ", "  areas: ")):
            found[key] = value.strip("\"'")
        seen.add(line.split(":")[0])
    return found, end + 1


def names(value):
    return value.split(", ") if value else []


class Check:
    def __init__(self, root, release):
        self.root, self.release, self.failures = Path(root), Path(release), []

    def fail(self, where, message):
        self.failures.append(f"{where}: {message}")

    def run(self, changed=None, jobs=()):
        roles_file = self.root / "v2" / "roles.md"
        self.roles = {row[0] for row in self.table(roles_file, "## Roles", 7)}
        rows = self.table(roles_file, "## Jobs", 4)
        self.jobs = {row[0]: row for row in rows}
        for job in sorted({row[0] for row in rows if [r[0] for r in rows].count(row[0]) > 1}):
            self.fail("v2/roles.md", f"job {job} is listed twice")
        self.rules = {}
        for path in sorted(p for p in (self.root / "v2/rules").glob("*/*.md") if p.name not in NOT_RULE_FILES):
            self.check_markers(path)
            for rule in read_rules(path, self.root, self.fail):
                self.check_rule(rule)
                if rule.id in self.rules:
                    self.fail(rule.where, f"{rule.id} is already defined at {self.rules[rule.id].where}")
                self.rules.setdefault(rule.id, rule)
        self.core_rules = {i: r for i, r in self.rules.items() if r.where.startswith("v2/rules/core/")}
        folders = sorted(p for p in (self.root / "v2" / "skills").iterdir() if p.is_dir())
        self.skills = {folder.name: self.check_template(folder) for folder in folders}
        self.check_jobs()
        for name in self.skills:
            self.check_release(name)
        for name in jobs:
            if name not in self.jobs:
                self.fail("--job", f"unknown job {name!r}")
        if changed is not None:
            self.check_version(changed)
        return self.failures

    def table(self, path, heading, width):
        """The rows of the table under a '## heading' line, as lists of cells. Each line up to the next heading must
        be blank, prose before the table, or a row of `width` cells with no other line between rows; else it fails."""
        lines = path.read_text(encoding="utf-8").split("\n")
        start = lines.index(heading) + 1
        rows, ended = [], False
        for number, line in enumerate(lines[start:], start=start + 1):
            if line.startswith("#"):
                break
            row = line.startswith("|") and line.endswith("|")
            if row and not ended:
                rows.append((number, [cell.strip() for cell in line[1:-1].split("|")]))
            elif line == "" or (not rows and PROSE.fullmatch(line)):
                ended = ended or bool(rows)
            else:
                self.fail(f"v2/roles.md:{number}", f"line has no allowed shape under {heading!r}: {line!r}")
        if len(rows) < 2 or len(rows[0][1]) != width or rows[1][1] != ["---"] * width:
            self.fail(f"v2/roles.md:{start}", f"the table under {heading!r} needs a header row and a rule line")
        for number, row in rows[2:]:
            if len(row) != width:
                self.fail(f"v2/roles.md:{number}", f"row needs {width} cells under {heading!r}")
        return [row for _, row in rows[2:] if len(row) == width]

    def check_markers(self, path):
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), start=1):
            if line == SECTION or any(marker in line for marker in MARKERS):
                self.fail(f"{path.relative_to(self.root).as_posix()}:{number}", "holds a copy marker")

    def check_rule(self, rule):
        needed = POINT_PARTS if rule.is_point else RULE_PARTS
        if rule.value("Status") == "retired":
            needed += ("Replaced by",)
        for name in needed:
            if not rule.value(name):
                self.fail(rule.where, f"{rule.id} has no {name}")
        for name in rule.twice:
            self.fail(rule.where, f"{rule.id} has {name} twice")
        if rule.value("Status") not in STATUSES:
            self.fail(rule.where, f"{rule.id} has Status {rule.value('Status')!r}, not one of {', '.join(STATUSES)}")
        if not rule.is_point and rule.value("Kind") not in KINDS:
            self.fail(rule.where, f"{rule.id} has Kind {rule.value('Kind')!r}, not one of {', '.join(KINDS)}")
        for role in rule.roles - self.roles - {EVERY_ROLE}:
            self.fail(rule.where, f"{rule.id} applies to unknown role {role!r}")

    def check_template(self, folder):
        where = f"v2/skills/{folder.name}"
        if (folder / "SKILL.md").exists():
            self.fail(f"{where}/SKILL.md", "a template is named SKILL.tmpl.md, never SKILL.md")
        template = folder / "SKILL.tmpl.md"
        if not template.is_file():
            self.fail(where, "has no SKILL.tmpl.md")
            return {"roles": [], "areas": []}
        found, body = metadata(template, lambda at, message: self.fail(f"{where}/{at}", message))
        roles = names(found.get("roles", ""))
        for role in roles:
            if role not in self.roles:
                self.fail(f"{where}/SKILL.tmpl.md", f"metadata.roles names unknown role {role!r}")
        for path in sorted(folder.rglob("*.md")):
            self.check_markers(path)
            lines = path.read_text(encoding="utf-8").split("\n")
            text = "\n".join(lines[body:] if path == template else lines)
            for rule_id in sorted(set(CITED.findall(text))):
                rule = self.core_rules.get(rule_id)  # the build copies CORE only
                status = rule.value("Status") if rule else "unknown"
                if status != "active":
                    self.fail(f"{where}/{path.relative_to(folder).as_posix()}", f"cites {rule_id}, which is {status}")
        return {"roles": roles, "areas": names(found.get("areas", ""))}

    def check_jobs(self):
        owner = {}
        for job, (_, roles, skills, rest) in self.jobs.items():
            skills, where = names(skills), f"v2/roles.md job {job}"
            for skill in skills:
                if skill not in self.skills:
                    self.fail(where, f"names {skill}, which has no skill folder")
                    continue
                if skill in owner:
                    self.fail(where, f"names {skill}, which job {owner[skill]} also names")
                owner[skill] = job
                if set(self.skills[skill]["roles"]) != set(names(roles)):
                    self.fail(where, f"{skill} has roles {self.skills[skill]['roles']}, not the job's {roles}")
            marked = [s for s in skills if s in self.skills and self.skills[s]["areas"] == [REST]]
            if marked != [rest]:
                self.fail(where, f"its `rest` skill is {rest}, but the templates mark {marked or 'none'}")
        for skill in self.skills:
            if skill not in owner:
                self.fail(f"v2/skills/{skill}", "is in no job")
        self.owner = owner

    def areas(self, name):
        """The skill's areas; for the `rest` skill, the CORE areas of its job's roles that no other skill lists."""
        skill = self.skills[name]
        if skill["areas"] != [REST] or name not in self.owner:
            return set(skill["areas"])
        row = self.jobs[self.owner[name]]
        listed = {a for s in names(row[2]) if s in self.skills for a in self.skills[s]["areas"]}
        return {r.area for r in self.core() if not r.is_point and r.roles & set(names(row[1]))} - listed

    def core(self):
        return [r for r in self.core_rules.values() if r.value("Status") == "active"]

    def check_release(self, name):
        path = self.release / name / "SKILL.md"
        if not path.is_file():
            self.fail(f"release/{name}", "has no SKILL.md; run the build")
            return
        copied = {m.group(1) for m in map(BEGIN.fullmatch, path.read_text(encoding="utf-8").split("\n")) if m}
        roles, areas = set(self.skills[name]["roles"]), self.areas(name)
        for rule in self.core():
            if rule.is_point or rule.id in copied:
                continue
            if EVERY_ROLE in rule.roles:
                self.fail(f"release/{name}/SKILL.md", f"misses {rule.id}, which applies to every role")
            elif rule.roles & roles and rule.value("Kind") == "floor":
                self.fail(f"release/{name}/SKILL.md", f"misses floor {rule.id}")
            elif rule.roles & roles and rule.area in areas:
                self.fail(f"release/{name}/SKILL.md", f"misses {rule.id} of area {rule.area}")
        for markdown in sorted((self.release / name).rglob("*.md")):
            self.check_bare(markdown, name)

    def check_bare(self, path, name):
        lines = path.read_text(encoding="utf-8").split("\n")
        start = lines.index("---", 1) + 1 if lines[0] == "---" else 0  # the frontmatter lists copied IDs
        where = f"release/{name}/{path.relative_to(self.release / name).as_posix()}"
        for number, line in enumerate(lines[:start], start=1):
            if TAG_LEFT.search(line):
                self.fail(f"{where}:{number}", f"holds a rule tag the build did not write out: {line!r}")
            elif CITED.search(line) and not line.startswith("  copied-ids: "):
                self.fail(f"{where}:{number}", f"the frontmatter names a rule ID only on its copied-ids line: {line!r}")
        inside = None
        for number, line in enumerate(lines[start:], start=start + 1):
            begin, end = BEGIN.fullmatch(line), END.fullmatch(line)
            if begin:
                inside = begin.group(1)
            elif end and end.group(1) == inside:
                inside = None
            elif inside is None:
                self.check_line(line, f"{where}:{number}")

    def check_line(self, line, where):
        """One release line outside the copied rules: no tag left, and a `Rules:` line of the one allowed shape."""
        if TAG_LEFT.search(line.replace(PLACEHOLDER, "")):
            self.fail(where, f"holds a rule tag the build did not write out; a release shows only {PLACEHOLDER}")
        if line.lstrip(" ").startswith("Rules:"):
            self.check_rules_line(line, where)
        elif CITED.search(line):
            self.fail(where, f"{CITED.search(line).group(1)} stands outside a `Rules:` line; a release cites a rule "
                             "only there")

    def check_rules_line(self, line, where):
        """After any indentation, "Rules:", then items separated by ",", each a space and then "ID (title)", and
        nothing else on the line."""
        rest = line.lstrip(" ")[len("Rules:"):]
        while rest.startswith(" "):
            rest = rest[1:]
            found = ITEM.match(rest)
            rule = self.core_rules.get(found.group(1)) if found else None
            item = rule and f"{rule.id} ({rule.title})"
            if not item or not rest.startswith(item):
                break
            rest = rest[len(item):]
            if rest == "":
                return
            if not rest.startswith(","):
                break
            rest = rest[1:]
        self.fail(where, "a `Rules:` line holds only \"ID (title)\" items separated by \", \", on one line: "
                         f"{line!r}")

    def check_version(self, changed):
        rules = [p for p in changed if re.fullmatch(r"v2/rules/[^/]+/[^/]+\.md", p)
                 and p.rsplit("/", 1)[1] not in NOT_RULE_FILES]
        if rules and "v2/VERSION" not in changed:
            self.fail(rules[0], "a rule file changed but v2/VERSION did not")


def main(argv=None):
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=root, type=Path)
    parser.add_argument("--release", type=Path, help="the release folder; default ROOT/release")
    parser.add_argument("--changed", type=Path, help="a file listing the changed paths, one per line")
    parser.add_argument("--job", action="append", default=[], help="a job name a pipeline step names")
    args = parser.parse_args(argv)
    changed = None
    if args.changed:
        changed = [line.strip() for line in args.changed.read_text(encoding="utf-8").split("\n") if line.strip()]
    try:
        failures = Check(args.root, args.release or args.root / "release").run(changed, args.job)
    except (OSError, ValueError, UnicodeDecodeError) as error:
        failures = [f"cannot read: {error}"]
    for failure in failures:
        print(f"check failed: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
