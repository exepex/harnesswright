"""Read a skill folder, and check that a folder is sound to copy into an arm (doc 11, Worlds).

Two rules, each a list of what is allowed:

- **Frontmatter** is read from one stated subset of YAML, with only the fields of `HW-PORT-01`
  ([10 · Skills](../../docs/design/10-skills.md)). Anything else is refused with its line number, so a value is
  never read short or read as the wrong type: the index row and the fingerprint are built from it.
- **Folders** hold only folders, regular files and links that lead, step by step through real folders, to a real
  folder or file inside the folder. A skill folder holds no links at all.
"""

import os
import re
from pathlib import Path, PurePosixPath

import manifest
from cases import PATH_PART, CaseError, is_name

SCALARS = ("name", "description", "license", "compatibility")
MAPPINGS = ("metadata",)
KEY = re.compile(r"([a-z][a-z-]*):(?: (.*))?")
# A metadata key: lower-case words joined by `-`, and never a spelling YAML reads as a typed value (TYPED).
META = re.compile(r"  ([a-z][a-z0-9]*(?:-[a-z0-9]+)*): (.*)")
# A plain one-line value: words separated by single spaces. A word holds no space or tab, never starts with `#`,
# and holds a colon only between two other characters (`file:line`). The first word starts with a letter, a digit
# or `(`. YAML reads every value of this shape as the same text, unless it is spelled like a typed value (TYPED).
WORD = r"[^\s:#][^\s:]*(?::[^\s:]+)*"
PLAIN = re.compile(rf"[\w(][^\s:]*(?::[^\s:]+)*(?: {WORD})*")
# The plain spellings that YAML reads as null, a boolean, a number or a date, from the YAML 1.1 and 1.2 schemas.
# A value or metadata key spelled like one of these is not text, so it is refused.
TYPED = re.compile(r"(?i:null|~|true|false|yes|no|on|off|y|n)|[-+]?(?:\.inf|\.Inf|\.INF)|\.nan|\.NaN|\.NAN"
                   r"|[-+]?(?:[0-9][0-9_]*(?::[0-5]?[0-9])*(?:\.[0-9_]*)?|\.[0-9_]+)(?:[eE][-+]?[0-9]+)?"
                   r"|0x[0-9a-fA-F_]+|0o[0-7_]+|0b[01_]+|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[Tt ].*)?")


def skill_files(skill_dir, name=None):
    """The skill's files as {relative path: bytes}, and its frontmatter.

    The folder must be sound with no links. The frontmatter name must be a skill name, and `name` when one is
    given: the name chooses where the host discovers the skill, so it must never be a path.
    """
    skill_dir = Path(skill_dir)
    problems = structure(skill_dir, links=False)
    if problems:
        raise CaseError(f"{skill_dir}: the skill is unsound: {problems}")
    files = {p.relative_to(skill_dir).as_posix(): p.read_bytes() for p in sorted(skill_dir.rglob("*")) if p.is_file()}
    if "SKILL.md" not in files:
        raise CaseError(f"{skill_dir}: no SKILL.md")
    try:
        meta = frontmatter(files["SKILL.md"].decode("utf-8"))
    except (UnicodeDecodeError, CaseError) as error:
        raise CaseError(f"{skill_dir}/SKILL.md: {error}") from None
    if not meta.get("name") or not meta.get("description"):
        raise CaseError(f"{skill_dir}: SKILL.md frontmatter needs name and description")
    if not is_name(meta["name"]) or (name is not None and meta["name"] != name):
        wanted = repr(name) if name is not None else "a skill name"
        raise CaseError(f"{skill_dir}: frontmatter name {meta['name']!r} must be {wanted}")
    return files, meta


def frontmatter(text):
    """The fields of a SKILL.md frontmatter block, or CaseError for anything outside the subset.

    The subset: a first line `---`, then fields at the left margin, then a line that is exactly `---`. Each field
    appears once. `name`, `description`, `license` and `compatibility` hold one plain value on the same line.
    `metadata` holds lines of `  key: value`, each value plain. Blank lines may sit between fields. There are no
    quoted values, block scalars or comments: YAML reads every value in the subset as exactly the text written.
    """
    # Lines end only at \n (a \r before it is dropped). Any other control or line-break character is refused, so
    # nothing can end a value or the block early.
    lines = [line[:-1] if line.endswith("\r") else line for line in text.split("\n")]
    for number, line in enumerate(lines, 1):
        if any(not char.isprintable() and char != "\t" for char in line):
            raise CaseError(f"frontmatter line {number}: holds a control or line-break character")
        if line == "---" and number > 1:
            break
    if not lines or lines[0] != "---":
        raise CaseError("no frontmatter: the first line must be ---")
    meta, mapping = {}, None
    for number, line in enumerate(lines[1:], 2):
        if line == "---":
            return meta
        if not line.strip():
            continue
        if line[0] == " ":
            found = META.fullmatch(line)
            if mapping is None or not found or TYPED.fullmatch(found.group(1)):
                raise CaseError(f"frontmatter line {number}: an indented line that is not `  key: value` in metadata")
            if found.group(1) in mapping:
                raise CaseError(f"frontmatter line {number}: metadata key {found.group(1)!r} appears twice")
            mapping[found.group(1)] = _plain(found.group(2), number)
            continue
        found = KEY.fullmatch(line)
        if not found or found.group(1) not in SCALARS + MAPPINGS:
            raise CaseError(f"frontmatter line {number}: not a field of HW-PORT-01 ({', '.join(SCALARS + MAPPINGS)})")
        key, value = found.group(1), found.group(2) or ""
        if key in meta:
            raise CaseError(f"frontmatter line {number}: {key} appears twice")
        if key in MAPPINGS:
            if value:
                raise CaseError(f"frontmatter line {number}: {key} holds indented `key: value` lines")
            meta[key] = mapping = {}
        else:
            meta[key], mapping = _plain(value, number), None
    raise CaseError("the frontmatter has no closing --- line")


def _plain(value, number):
    """A plain one-line value that YAML reads as exactly this text."""
    if PLAIN.fullmatch(value) and not TYPED.fullmatch(value):
        return value
    raise CaseError(f"frontmatter line {number}: {value!r} is not plain one-line text "
                    "(no quotes, block scalars, comments or typed values)")


def structure(folder, links=True):
    """Every entry of `folder` that is not allowed. An empty list means the folder is sound to copy.

    Allowed: folders, regular files, and, when `links` is true, relative links whose target leads step by step
    through real folders of `folder` to a real folder or file in it. A link is judged by its text against the
    folder's manifest, never by resolving it on disk, so it stays right when the folder is copied. A `.git` folder
    is never allowed: declare history as commits in case.json.
    """
    try:
        entries = manifest.manifest(folder)
    except manifest.Unreadable as error:
        return [str(error)]
    problems = []
    for path, entry in sorted(entries.items()):
        if ".git" in path.split("/"):
            if PurePosixPath(path).name == ".git":
                problems.append(f"{path}: a .git folder; declare history as commits in case.json")
        elif manifest.kind(entry) == "link":
            if not links:
                problems.append(f"{path}: a link; a skill folder holds only folders and files")
            elif not _leads_inside(entries, path, entry[len("link "):]):
                problems.append(f"{path}: a link that does not lead to a folder or file inside the folder")
    return problems


def _leads_inside(entries, path, target):
    """True when `target`, read from the folder that holds `path`, is made only of `..` and name steps, passes only
    through real folders, and ends at a real folder or file. A step through a link is refused, so links never chain
    out of the folder, and a target cannot dangle."""
    steps = target.split("/")
    if not all(step == ".." or (PATH_PART.fullmatch(step) and step not in (".", ".git")) for step in steps):
        return False
    at = list(PurePosixPath(path).parent.parts)
    for number, step in enumerate(steps, 1):
        if step == "..":
            if not at:
                return False
            at.pop()
        else:
            at.append(step)
        kind = manifest.kind(entries.get("/".join(at), "missing")) if at else "dir"
        if kind not in (("dir", "file") if number == len(steps) else ("dir",)):
            return False
    return True
