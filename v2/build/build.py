"""Build release/ from the skill templates and the CORE rulebook.

Standard library only. The build is a pure function of the templates (v2/skills/<name>/), the CORE layer
(v2/rules/core/), the roles file (v2/roles.md) and the version file (v2/VERSION). Output is sorted, uses LF line
endings and carries no timestamps, so building twice gives the same bytes (reviews/release-design/final-design.md
sections 1, 2 and 5; plan/b01-plan.md part c).

For each skill folder it writes release/<name>/:
- SKILL.md: the template's frontmatter with generated metadata added, the "Generated from" header, the template's
  title line, the one copied section (copyform.rules_section), then the rest of the body. Each rule tag and each
  cited ID outside the copied section becomes "ID (title)" (tags.py). The content hash and size-rest cover the
  whole file except the generated metadata lines; size-floors counts the copied floors.
- every other Markdown file, expanded the same way (header and citations, no copied section);
- scripts/ and licence files: the skill's own, and the shipped modules, copied byte for byte.
Then release/manifest.json, which also names each skill's job and whether it is the job's `rest` skill. Any
file the skill folder holds outside that list fails the build. Last, what the standards reader reads at run time
(plan/b01-plan.md part e0), byte for byte: every layer folder under v2/rules/ as release/rules/<folder>/, and
v2/roles.md as release/roles.md.

The manifest also says what each file is, so a reader can prove a copy byte for byte: `files`, the sha256 of every
file of each skill folder, `run-time`, the one list of what a run reads from the release besides the skill
(`RUN_TIME`; resolve.py reads it from the manifest it ships with and reads nothing else there), and `run-time-files`,
the sha256 of every file the list covers. manifest.json is on the list but cannot hold its own hash.

Run: python3 v2/build/build.py [--root ROOT] [--out OUT]
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import copyform
import reach
import rulebook
import tags
from resolve import covers

SHIPPED = ("rulebook.py", "reach.py", "copyform.py", "repoprofile.py", "resolve.py", "runfiles.py")
GENERATED = ("copied-ids", "rulebook-version", "content-hash", "size-floors", "size-rest")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
TEMPLATE = "SKILL.tmpl.md"
RUN_TIME = ("manifest.json", "roles.md", "rules/")  # what a run reads from the release; declared here only
LAYOUT = tuple(p.rstrip("/") for p in RUN_TIME)  # release/ holds these and one folder per skill, nothing else
LAYER_FILE = re.compile(r"[a-z0-9-]+\.(?:md|yaml)")  # a layer folder holds rule files, its index, layer.yaml
LICENCE = re.compile(r"LICENSE(?:-[A-Za-z0-9.]+)?\.txt")  # an adapted skill keeps its source's licence notice
SCRIPT = re.compile(r"scripts/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.(?:py|sh)")  # HW-PORT-04: Python or POSIX sh


class BuildError(rulebook.RulebookError):
    """A template, skill folder or version the build cannot turn into a release."""


def read_version(path):
    lines = rulebook.read_lines(path)
    if len(lines) != 1 or not VERSION.fullmatch(lines[0]):
        raise BuildError(f"{path}: must hold one version line such as 0.1.0")
    return lines[0]


def skill_files(folder):
    """(Markdown files, files copied byte for byte) of one skill folder, as sorted relative paths.

    Allowed: Markdown files (not SKILL.md), `.py` and `.sh` files under scripts/, and licence files at the root.
    Any other file fails the build."""
    markdown, scripts = [], []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        rel = path.relative_to(folder).as_posix()
        if SCRIPT.fullmatch(rel) or LICENCE.fullmatch(rel):
            scripts.append(rel)
        elif rel.endswith(".md") and not rel.startswith("scripts/") and rel != "SKILL.md":
            markdown.append(rel)
        else:
            raise BuildError(f"{folder.name}/{rel}: a skill folder holds only {TEMPLATE}, other Markdown files, "
                             "licence files and .py or .sh files under scripts/")
    if TEMPLATE not in markdown:
        raise BuildError(f"{folder.name}: has no {TEMPLATE}")
    shipped = [s for s in scripts if s.removeprefix("scripts/") in SHIPPED]
    if shipped:
        raise BuildError(f"{folder.name}/{shipped[0]}: has the name of a shipped module")
    return markdown, scripts


def header(source, version):
    return f"<!-- Generated from {source} at version {version}. Do not edit. -->"


def frontmatter_with(lines, end, generated):
    """The template's frontmatter lines with the generated metadata lines after the last metadata line."""
    start = lines.index("metadata:")
    last = start
    while last + 1 < end and lines[last + 1].startswith("  "):
        last += 1
    added = [f'  {key}: "{value}"' for key, value in generated]
    return lines[:last + 1] + added + lines[last + 1:end + 1]


def build_skill(folder, rel_folder, layer, version, row, skills):
    """The files of one release skill, as relative path -> bytes, and its manifest entry."""
    name = folder.name
    markdown, scripts = skill_files(folder)
    data, body_start = rulebook.read_frontmatter(folder / TEMPLATE)
    taken = [key for key in GENERATED if key in data.get("metadata", {})]
    if taken:
        raise BuildError(f"{name}/{TEMPLATE}: metadata.{taken[0]} is written by the build")
    rules = list(layer.rules.values())
    lines = rulebook.read_lines(folder / TEMPLATE)
    titles = {rule.id: rule.title for rule in rules}
    texts = {rel: "\n".join(rulebook.read_lines(folder / rel)) + "\n" for rel in markdown}
    texts[TEMPLATE] = "\n".join(lines[body_start:])  # the frontmatter cites nothing
    tags.check_frontmatter(lines[:body_start], f"{name}/{TEMPLATE}")
    expanded = {rel: tags.expand(text, titles, f"{name}/{rel}", body_start + 1 if rel == TEMPLATE else 1)
                for rel, text in texts.items()}  # fails an unknown ID or a tag with no allowed shape, naming the line
    cited = set().union(*(tags.ids(text) for text in texts.values()))
    areas = reach.areas_of(skills[name], row, skills, rules)
    reached = reach.reach(rules, skills[name].roles, areas, cited)
    files = {}
    for rel in markdown:
        if rel != TEMPLATE:
            files[rel] = f"{header(f'{rel_folder}/{rel}', version)}\n\n{expanded[rel]}"
    body = expanded[TEMPLATE].split("\n")  # expanding keeps every line in its place
    first = next((i for i, line in enumerate(body) if line.strip()), 0)
    title_at = first if first < len(body) and body[first].startswith("# ") else -1  # the title is the first line
    before, after = body[:title_at + 1], body[title_at + 1:]
    section = copyform.rules_section(reached).rstrip("\n")
    parts = ["\n".join([header(f"{rel_folder}/{TEMPLATE}", version), *before]), section,
             "\n".join(after).strip("\n")]
    text = "\n\n".join(part for part in parts if part) + "\n"
    floors = "\n\n".join(copyform.copy_rule(r) for r in reached.floors)
    copied = [r.id for r in reached.floors] + [r.id for r in reached.others
                                                if not r.is_decision_point or r.id in reached.cited_points]
    counted = "\n".join(lines[:body_start]) + "\n" + text  # all but the generated metadata, which cannot hold itself
    entry = {"job": row["Job"], "rest": skills[name].is_rest, "roles": list(skills[name].roles),
             "areas": sorted(areas), "copied-ids": copied, "rulebook-version": version,
             "content-hash": hashlib.sha256(counted.encode("utf-8")).hexdigest(),
             "size-floors": reach.size(floors), "size-rest": reach.size(counted) - reach.size(floors)}
    generated = [(key, ", ".join(entry[key]) if key == "copied-ids" else entry[key]) for key in GENERATED]
    head = frontmatter_with(lines, body_start - 1, generated)
    files["SKILL.md"] = "\n".join(head) + "\n" + text
    for rel in scripts:
        files[rel] = (folder / rel).read_bytes()
    return files, entry


def build(root):
    """Every release file, as path under release/ -> str or bytes."""
    root = Path(root)
    version = read_version(root / "v2" / "VERSION")
    layer = rulebook.read_layer(root / "v2" / "rules" / "core")
    jobs = rulebook.read_roles(root / "v2" / "roles.md")["jobs"]
    folders = sorted(p for p in (root / "v2" / "skills").iterdir() if p.is_dir())
    skills = {}
    for folder in folders:
        if folder.name in LAYOUT:
            raise BuildError(f"{folder}: `{folder.name}` is a release file or folder, not a skill name")
        skill_files(folder)
        skills[folder.name] = reach.read_skill(folder.name, rulebook.read_frontmatter(folder / TEMPLATE)[0])
    owner = reach.check_jobs(jobs, skills)
    files, manifest = {}, {"rulebook-version": version, "skills": {}}
    for folder in folders:
        built, entry = build_skill(folder, f"v2/skills/{folder.name}", layer, version, owner[folder.name], skills)
        files.update({f"{folder.name}/{rel}": content for rel, content in built.items()})
        manifest["skills"][folder.name] = entry
    for folder in folders:
        for module in SHIPPED:
            files[f"{folder.name}/scripts/{module}"] = (Path(__file__).parent / module).read_bytes()
    files.update(layer_files(root / "v2" / "rules"))
    files["roles.md"] = (root / "v2" / "roles.md").read_bytes()
    for name, entry in manifest["skills"].items():
        entry["files"] = {rel[len(name) + 1:]: sha256(files[rel]) for rel in files if rel.startswith(f"{name}/")}
    manifest["run-time"] = list(RUN_TIME)
    manifest["run-time-files"] = {rel: sha256(content) for rel, content in files.items() if run_time(rel)}
    files["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return files


def sha256(content):
    return hashlib.sha256(content if isinstance(content, bytes) else content.encode("utf-8")).hexdigest()


def run_time(rel):
    """True for a release path the run-time list covers, other than manifest.json, which cannot hash itself."""
    return rel != "manifest.json" and covers(RUN_TIME, rel)


def layer_files(rules):
    """Each layer folder's files, byte for byte, as rules/<folder>/<file>. A layer folder holds files only."""
    files = {}
    for folder in sorted(p for p in rules.iterdir() if p.is_dir()):
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.is_symlink() or not LAYER_FILE.fullmatch(path.name):
                raise BuildError(f"{path}: a layer folder holds only .md and .yaml files")
            files[f"rules/{folder.name}/{path.name}"] = path.read_bytes()
    return files


def is_copy(rel):
    """True for a release file the build copies byte for byte from its source."""
    return "/scripts/" in rel or rel.startswith("rules/") or rel == "roles.md"


def write(out, files):
    """Write the files under out and remove any other file there except .gitkeep. Fails on a symbolic link there,
    so nothing outside out is written."""
    out = Path(out)
    links = [p for p in [out, *(out.rglob("*") if out.is_dir() else [])] if p.is_symlink()]
    if links:
        raise BuildError(f"{links[0]}: the output folder must hold no symbolic link")
    for rel, content in files.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        path.write_bytes(data)
    for path in sorted(out.rglob("*"), reverse=True):
        rel = path.relative_to(out).as_posix()
        if path.is_file() and rel not in files and rel != ".gitkeep":
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def main(argv=None):
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=root)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    try:
        write(args.out or Path(args.root) / "release", build(args.root))
    except rulebook.RulebookError as error:
        print(f"build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
