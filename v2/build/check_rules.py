"""Check the rulebook, the roles file, the templates, and the floors and areas each release skill copies.

Standard library only. It imports nothing from the build: it reads rule files, the roles file and frontmatter by
its own, simpler method, so a fault in the build's reader cannot hide itself (reviews/release-design/final-design.md
section 5; plan/b01-plan.md part d1). It collects every failure, prints each as "check failed: <where>: <what>" and
returns 1; with none it returns 0. It fails:
- a rule without a part its kind needs, and an Applies to or metadata.roles naming a role v2/roles.md does not list;
- a copy marker in a rule file or in a skill folder's Markdown, and a skill folder holding SKILL.md;
- a template or its Markdown citing an ID that is unknown, retired or inferred;
- a Jobs row that does not match the skill folders: each skill in one job, with its job's roles, and exactly one
  `rest` skill, the one the row names;
- a release SKILL.md missing a CORE floor of its roles, an every-role rule, or a rule of its roles in one of its
  areas; and a bare ID (one without " (title)") outside the copied blocks of a release Markdown file;
- a job name given with --job that the Jobs table does not list;
- with --changed, a changed rule file when v2/VERSION is not in the same list.

Run: python3 v2/build/check_rules.py [--root ROOT] [--release DIR] [--changed FILE] [--job NAME]...
"""

import argparse
import re
import sys
from pathlib import Path

EVERY_ROLE = "every role"
REST = "rest"
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
MARKERS = ("<!-- rule ", "<!-- end ", "<!-- Generated from ")
SECTION = "## Rules for this skill"


class Rule:
    def __init__(self, rule_id, title, where):
        self.id, self.title, self.where, self.parts = rule_id, title, where, {}

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


def read_rules(path, root):
    """Rules of one file: a rule starts at a '### ID · title' line, a part at a '- **Name:**' line; every other
    line belongs to the part above it."""
    rules, rule, part = [], None, None
    lines = path.read_text(encoding="utf-8").split("\n")
    for number, line in enumerate(lines, start=1):
        heading, found = HEADING.fullmatch(line), PART.fullmatch(line)
        if heading:
            rule, part = Rule(*heading.groups(), f"{path.relative_to(root).as_posix()}:{number}"), None
            rules.append(rule)
        elif rule is not None and found:
            part = found.group(1)
            rule.parts[part] = found.group(2) or ""
        elif rule is not None and part is not None and line.strip():
            rule.parts[part] += "\n" + line
    return rules


def rule_files(root):
    return sorted(p for p in (root / "v2" / "rules").glob("*/*.md") if p.name not in NOT_RULE_FILES)


def table(path, heading, width):
    """The rows of the table under a '## heading' line, as lists of cells."""
    lines = path.read_text(encoding="utf-8").split("\n")
    start = lines.index(heading) + 1
    rows = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.startswith("|"):
            rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return [row for row in rows[2:] if len(row) == width]


def metadata(path):
    """The name and the metadata keys of a frontmatter block, quotes removed."""
    lines = path.read_text(encoding="utf-8").split("\n")
    end = lines.index("---", 1)
    found = {}
    for line in lines[1:end]:
        key, _, value = line.strip().partition(": ")
        if line.startswith(("name: ", "  roles: ", "  areas: ")):
            found[key] = value.strip("\"'")
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
        self.roles = {row[0] for row in table(roles_file, "## Roles", 7)}
        self.jobs = {row[0]: row for row in table(roles_file, "## Jobs", 4)}
        self.rules = {}
        for path in rule_files(self.root):
            self.check_markers(path)
            for rule in read_rules(path, self.root):
                self.check_rule(rule)
                self.rules.setdefault(rule.id, rule)
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
        found, body = metadata(template)
        roles = names(found.get("roles", ""))
        for role in roles:
            if role not in self.roles:
                self.fail(f"{where}/SKILL.tmpl.md", f"metadata.roles names unknown role {role!r}")
        for path in sorted(folder.rglob("*.md")):
            self.check_markers(path)
            lines = path.read_text(encoding="utf-8").split("\n")
            text = "\n".join(lines[body:] if path == template else lines)
            for rule_id in sorted(set(CITED.findall(text))):
                rule = self.rules.get(rule_id)
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
        return [r for r in self.rules.values() if r.where.startswith("v2/rules/core/")
                and r.value("Status") == "active"]

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
        inside = None
        for number, line in enumerate(lines[start:], start=start + 1):
            begin, end = BEGIN.fullmatch(line), END.fullmatch(line)
            if begin:
                inside = begin.group(1)
            elif end and end.group(1) == inside:
                inside = None
            elif inside is None:
                for found in CITED.finditer(line):
                    rule = self.rules.get(found.group(1))
                    where = f"release/{name}/{path.relative_to(self.release / name).as_posix()}:{number}"
                    if rule is None:
                        self.fail(where, f"{found.group(1)} is not in the rulebook")
                    elif not line[found.end():].startswith(f" ({rule.title})"):
                        self.fail(where, f"{rule.id} is bare; a release writes it as \"{rule.id} ({rule.title})\"")

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
