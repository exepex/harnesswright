"""Check release/ against its sources, and summarise each skill's change against a base manifest.

Standard library only. It imports only check_rules.py, its sibling, and runs build.py as a subprocess for the
rebuild comparison (plan/b01-plan.md, "Where things live" and part d2; reviews/release-design/final-design.md
section 5). It collects every failure, prints each as "check failed: <where>: <what>" and returns 1; with none it
returns 0. Each `check_*` method covers one kind of failure:
- the rebuild: release/ must equal what build.py writes from the sources, byte for byte;
- each copied block against its rule, read by check_rules' own reader: prose compared with whitespace collapsed,
  code blocks exactly;
- the manifest against the release skills: the same skills, and per skill the same metadata, with the hash, the
  sizes and the copied IDs recounted here from the SKILL.md text;
- the Agent Skills format of each release SKILL.md (CORE-TEMPLATE-03), and the recorded sizes against the 30,000
  code point ceilings (CORE-TEMPLATE-02);
- an expanded reference file over 500 lines, named by its source.
With --base, it prints a summary per skill to standard output: rules added and removed, a removed floor flagged,
and the size change.

Run: python3 v2/build/check_release.py [--root ROOT] [--release DIR] [--base MANIFEST]
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from check_rules import BEGIN, END, FRONT, NOT_RULE_FILES, read_rules

CEILING = 30000
REFERENCE_LINES = 500
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
FIELDS = ("name", "description", "license", "compatibility", "metadata")
GENERATED = ("copied-ids", "rulebook-version", "content-hash", "size-floors", "size-rest")
RULE_LABELS = (("Kind", "Kind"), ("Rule", "Rule"), ("Exceptions", "Exceptions"), ("Good", "Good"),
               ("Bad", "Bad (do not do this)"))
POINT_LABELS = (("Question", "Question"), ("Options", "Options"), ("Default", "Default"))
BINDING = "The binding in your rules text wins; the default applies only when unbound."
LABEL = re.compile(r"- \*\*([^*]+):\*\*(?: (.*))?")
HEADER = re.compile(r"<!-- Generated from (\S+) at version \S+\. Do not edit\. -->")
FLOORS, OTHERS = "### Floors", "### Other rules"


def lines_of(text):
    """A part's lines: the first line, then each continuation without its 2-space indent."""
    first, *rest = text.split("\n")
    return [first] + [line[2:] for line in rest]


def compared(lines):
    """Prose with whitespace collapsed, and each code-block line exactly, as one list."""
    out, words, code = [], [], False
    for line in lines:
        fence = line.lstrip().startswith("```")
        if code or fence:
            if words:
                out.append(" ".join(words))
                words = []
            out.append(("code", line))
            code = code != fence
        else:
            words += line.split()
    return out + ([" ".join(words)] if words else [])


def frontmatter(lines):
    """Top-level keys and metadata keys of a frontmatter block, with the index of its closing line."""
    end = lines.index("---", 1)
    top, meta = {}, {}
    for line in lines[1:end]:
        key, _, value = line.strip().partition(": ")
        if line == "metadata:":
            top["metadata"] = ""
        elif line.startswith("  "):
            meta[key] = value
        else:
            top[key] = value
    return top, meta, end


def unquote(value):
    return value[1:-1] if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'" else value


class ReleaseCheck:
    def __init__(self, root, release):
        self.root, self.release, self.failures = Path(root), Path(release), []

    def fail(self, where, message):
        self.failures.append(f"{where}: {message}")

    def run(self, base=None):
        """The failures, and the summary lines when a base manifest is given."""
        self.rules = {}
        for path in sorted(p for p in (self.root / "v2/rules/core").glob("*.md") if p.name not in NOT_RULE_FILES):
            for rule in read_rules(path, self.root, self.fail):
                self.rules.setdefault(rule.id, rule)
        self.check_rebuild()
        manifest = json.loads((self.release / "manifest.json").read_text(encoding="utf-8"))
        skills = sorted(p.name for p in self.release.iterdir() if p.is_dir())
        if sorted(manifest.get("skills", {})) != skills:
            self.fail("release/manifest.json", f"lists {sorted(manifest.get('skills', {}))}, not the skills {skills}")
        for name in skills:
            path = self.release / name / "SKILL.md"
            if not path.is_file():
                self.fail(f"release/{name}", "has no SKILL.md")
                continue
            lines = path.read_text(encoding="utf-8").split("\n")
            top, meta, end = frontmatter(lines)
            self.check_format(name, top, meta)
            self.check_blocks(name, lines[end + 1:])
            self.check_manifest(name, lines, meta, manifest["skills"].get(name, {}))
            self.check_references(name)
        return self.failures, (self.summary(manifest, base) if base is not None else [])

    def check_rebuild(self):
        with tempfile.TemporaryDirectory() as out:
            done = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("build.py")), "--root",
                                   str(self.root), "--out", out], capture_output=True, text=True)
            if done.returncode != 0:
                self.fail("build.py", f"the rebuild failed: {done.stderr.strip()}")
                return
            built = {p.relative_to(out).as_posix(): p.read_bytes() for p in Path(out).rglob("*") if p.is_file()}
        kept = {p.relative_to(self.release).as_posix(): p.read_bytes() for p in self.release.rglob("*")
                if p.is_file() and p.name != ".gitkeep"}
        for rel in sorted(set(built) | set(kept)):
            if rel not in kept:
                self.fail(f"release/{rel}", "is missing; run the build")
            elif rel not in built:
                self.fail(f"release/{rel}", "is not made by the build")
            elif built[rel] != kept[rel]:
                self.fail(f"release/{rel}", "differs from a rebuild; run the build and commit release/")

    def blocks(self, body):
        """(ID, line number, lines) of each copied block in a SKILL.md body."""
        found, start = [], None
        for number, line in enumerate(body):
            begin, end = BEGIN.fullmatch(line), END.fullmatch(line)
            if begin:
                start = (begin.group(1), number)
            elif end and start and end.group(1) == start[0]:
                found.append((start[0], start[1], body[start[1] + 1:number]))
                start = None
        return found

    def check_blocks(self, name, body):
        for rule_id, number, lines in self.blocks(body):
            where = f"release/{name}/SKILL.md block {rule_id}"
            rule = self.rules.get(rule_id)
            if rule is None or rule.value("Status") != "active":
                self.fail(where, "copies a rule that is not an active CORE rule")
                continue
            if lines[:2] != [f"#### {rule.id} · {rule.title}", ""]:
                self.fail(where, f"does not start with the heading \"#### {rule.id} · {rule.title}\"")
            parts, part, extra = {}, None, []
            for line in lines[2:]:
                label = LABEL.fullmatch(line)
                if label:
                    part = label.group(1)
                    parts[part] = label.group(2) or ""
                elif part is not None and (line.startswith("  ") or line == ""):
                    parts[part] += "\n" + line
                else:
                    extra.append(line)
            labels = POINT_LABELS if rule.is_point else RULE_LABELS
            wanted = [(name_, label) for name_, label in labels if name_ in rule.parts]
            if list(parts) != [label for _, label in wanted]:
                self.fail(where, f"holds the parts {list(parts)}, not {[label for _, label in wanted]}")
            if extra != ([BINDING] if rule.is_point else []):
                self.fail(where, f"holds other text: {extra}")
            for part_name, label in wanted:
                if label in parts and compared(lines_of(parts[label])) != compared(lines_of(rule.parts[part_name])):
                    self.fail(where, f"its {label} differs from the rule in {rule.where}")

    def check_manifest(self, name, lines, meta, entry):
        where = f"release/{name}"
        text = "\n".join(lines)
        body = "\n".join(line for line in lines if not any(line.startswith(f"  {key}: ") for key in GENERATED))
        floors = text[text.index(FLOORS) + len(FLOORS) + 2:text.index(OTHERS) - 2] if FLOORS in text else ""
        ids = [rule_id for rule_id, _, _ in self.blocks(lines)]
        counted = {"copied-ids": ", ".join(ids), "rulebook-version": self.version(),
                   "content-hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                   "size-floors": str(len(floors)), "size-rest": str(len(body) - len(floors))}
        for key in GENERATED:
            recorded = unquote(meta.get(key, ""))
            listed = entry.get(key)
            listed = ", ".join(listed) if isinstance(listed, list) else str(listed)
            if recorded != counted[key]:
                self.fail(f"{where}/SKILL.md", f"metadata.{key} is {recorded!r}; its text gives {counted[key]!r}")
            if listed != counted[key]:
                self.fail("release/manifest.json", f"{name} {key} is {listed!r}; its SKILL.md gives {counted[key]!r}")
            if key.startswith("size-") and recorded.isdigit() and int(recorded) > CEILING:
                self.fail(f"{where}/SKILL.md", f"{key} is {recorded}, over the ceiling of {CEILING} (CORE-TEMPLATE-02)")

    def version(self):
        return (self.root / "v2/VERSION").read_text(encoding="utf-8").strip()

    def check_format(self, name, top, meta):
        where = f"release/{name}/SKILL.md"
        for key in top:
            if key not in FIELDS:
                self.fail(where, f"frontmatter field {key!r} is not in the Agent Skills format (CORE-TEMPLATE-03)")
        skill = unquote(top.get("name", ""))
        if skill != name or not NAME.fullmatch(skill) or len(skill) > 64:
            self.fail(where, f"name {skill!r} must equal the folder name: at most 64 lowercase letters, digits and "
                             "single hyphens")
        description = unquote(top.get("description", ""))
        if not description or len(description) > 1024 or "<" in description or ">" in description:
            self.fail(where, "description must be 1 to 1024 characters with no '<' or '>'")
        if len(unquote(top.get("compatibility", ""))) > 500:
            self.fail(where, "compatibility is over 500 characters")
        for line in (f"{key}: {value}" for key, value in [*top.items(), *meta.items()] if key != "metadata"):
            if not FRONT.fullmatch(line):
                self.fail(where, f"frontmatter line has no allowed shape: {line!r}")

    def check_references(self, name):
        for path in sorted((self.release / name).rglob("*.md")):
            lines = path.read_text(encoding="utf-8").split("\n")
            if path.name != "SKILL.md" and len(lines) - 1 > REFERENCE_LINES:
                header = HEADER.fullmatch(lines[0])
                source = header.group(1) if header else "an unknown source"
                self.fail(f"release/{name}/{path.relative_to(self.release / name).as_posix()}",
                          f"has {len(lines) - 1} lines, over {REFERENCE_LINES}; split its source {source}")

    def summary(self, manifest, base):
        """One line per skill that changed: rules added and removed, removed floors flagged, sizes before -> after."""
        old, new, out = base.get("skills", {}), manifest.get("skills", {}), []
        for name in sorted(set(old) | set(new)):
            before, after = old.get(name, {}), new.get(name, {})
            added = [i for i in after.get("copied-ids", []) if i not in before.get("copied-ids", [])]
            removed = [i for i in before.get("copied-ids", []) if i not in after.get("copied-ids", [])]
            floors = [i for i in removed if i in self.rules and self.rules[i].value("Kind") == "floor"]
            sizes = [f"{key} {before.get(key, 0)} -> {after.get(key, 0)}" for key in ("size-floors", "size-rest")]
            if before == after:
                continue
            state = "new skill" if not before else "removed skill" if not after else "changed"
            line = f"{name}: {state}; added {', '.join(added) or 'none'}; removed {', '.join(removed) or 'none'}"
            out.append(f"{line}; {'; '.join(sizes)}" + (f"; FLOOR REMOVED: {', '.join(floors)}" if floors else ""))
        return out


def main(argv=None):
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=root, type=Path)
    parser.add_argument("--release", type=Path, help="the release folder; default ROOT/release")
    parser.add_argument("--base", type=Path, help="the base branch's release/manifest.json, for the summary")
    args = parser.parse_args(argv)
    try:
        base = json.loads(args.base.read_text(encoding="utf-8")) if args.base else None
        failures, summary = ReleaseCheck(args.root, args.release or args.root / "release").run(base)
    except (OSError, ValueError, KeyError, UnicodeDecodeError) as error:
        failures, summary = [f"cannot read: {error}"], []
    for line in summary:
        print(line)
    for failure in failures:
        print(f"check failed: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
