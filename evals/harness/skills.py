"""Read a skill folder, and check that a folder is sound to copy into an arm (doc 11, Worlds).

`frontmatter` reads one small, stated subset of YAML and refuses everything else, so a description is never
read short without a word: the index row and the fingerprint are built from it.
"""

import json
import os
import re
from pathlib import Path

from cases import CaseError, is_name

KEY = re.compile(r"([A-Za-z0-9_-]+):(?: (.*))?")
BLOCK = (">", "|", ">-", "|-", ">+", "|+")


def skill_files(skill_dir, name=None):
    """The skill's files as {relative path: bytes}, and its frontmatter.

    The frontmatter name must be a skill name, and `name` when one is given: the name chooses where the host
    discovers the skill, so it must never be a path.
    """
    skill_dir = Path(skill_dir)
    files = {p.relative_to(skill_dir).as_posix(): p.read_bytes()
             for p in sorted(skill_dir.rglob("*")) if p.is_file() and not p.is_symlink()}
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
    """The top-level values of a SKILL.md frontmatter block, or CaseError when it is outside the subset.

    The subset: a `---` line, then lines of `key: value` at the left margin, then a closing `---` line. A value is
    plain text on one line, a quoted string, or a block scalar (`>` or `|`, then indented lines, blank lines
    allowed), which is joined into one line. A key with no value may hold an indented mapping, such as
    `metadata`, which is kept as its raw lines. Blank lines may sit between keys.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise CaseError("no frontmatter: the first line must be ---")
    if "---" not in [line.strip() for line in lines[1:]]:
        raise CaseError("the frontmatter has no closing --- line")
    meta, key, mode = {}, None, None
    for number, line in enumerate(lines[1:], 2):
        if line.strip() == "---":
            return {k: v.strip() if isinstance(v, str) else v for k, v in meta.items()}
        if line[:1] in (" ", "\t") and line.strip():
            if mode is None:
                raise CaseError(f"frontmatter line {number}: an indented line after a one-line value; write the "
                                "value on one line or as a block scalar (>)")
            meta[key] = f"{meta[key]} {line.strip()}" if mode == "block" else meta[key] + [line.strip()]
            continue
        if not line.strip():
            continue
        found = KEY.fullmatch(line)
        if not found:
            raise CaseError(f"frontmatter line {number}: not a `key: value` line")
        key, value = found.group(1), (found.group(2) or "").strip()
        if value in BLOCK:
            meta[key], mode = "", "block"
        elif not value:
            meta[key], mode = [], "mapping"
        else:
            meta[key], mode = _scalar(value, number), None
    raise CaseError("the frontmatter has no closing --- line")


def _scalar(value, number):
    if value[0] not in "\"'":
        return value
    if len(value) < 2 or value[-1] != value[0]:
        raise CaseError(f"frontmatter line {number}: an unclosed quoted value")
    if value[0] == "'":
        return value[1:-1].replace("''", "'")
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        raise CaseError(f"frontmatter line {number}: a double-quoted value with escapes outside JSON") from None


def structure(folder):
    """A `.git` folder, an absolute symlink or a symlink that points outside `folder`.

    A link is judged by its text alone, from where it sits inside the folder, and never by resolving it on disk:
    the folder is copied into an arm, and a link that left and came back in through the folder's own name would
    point outside the copy.
    """
    problems = []
    folder = Path(folder)
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder).as_posix()
        if path.name == ".git":
            problems.append(f"{relative}: a .git folder; declare history as commits in case.json")
        if path.is_symlink():
            link = os.readlink(path)
            target = os.path.normpath(os.path.join(os.path.dirname(relative), link))
            if os.path.isabs(link):
                problems.append(f"{relative}: an absolute symlink; use a relative one inside the folder")
            elif target == ".." or target.startswith("../"):
                problems.append(f"{relative}: a symlink that points outside the folder")
    return problems
