#!/usr/bin/env python3
"""Check a claims file against the claims contract, the story and the change.

Run from the project root, the folder that holds .harness/:
  python3 claims_check.py --claims PATH [--story PATH] [--base REF] [--repo DIR]

Standard library only, no network, deterministic. Every line of the claims file must be a shape the contract allows
in its section (one table of shapes, SHAPES), or the check fails on it. Then it checks:
- the seven sections, in order, and the request quoted with `>`;
- one entry per requirement the story covers (its frontmatter `covers`), each with Status, Done, Evidence and Test
  types in that order, and a Status of `met`, `not met` or `not verified`;
- each test type the story's `tests` asks for, with a test (`path:line`) or an `OP-n` that Open proof items defines,
  and no `met` while an `OP-n` stands in for a test;
- each open proof item numbered in order, with Unproven, Proof and Owner;
- each file under Files changed: its true line count (as `wc -l`), or that it is gone when marked deleted; with
  --base, the list equals what git reports as changed since REF, plus untracked files, outside .harness/runs/;
- each `path:line` outside the request and outside code blocks: the file exists and has that line.
It does not check Standards yet; it says so.

The story is --story, else <run folder>/stories/<claims file name>. Exit 0: no failure; each "not checked:" line names
a check that did not run, for Not verified. Exit 1: each "fail:" line names a fault. Exit 2: an input is missing or
cannot be read.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

SECTIONS = ("Request", "Requirements", "Open proof items", "Standards", "Out of scope", "Files changed",
            "Not verified")
FIELDS = {"Requirements": ("Status", "Done", "Evidence", "Test types"),
          "Open proof items": ("Unproven", "Proof", "Owner")}
STATUSES = ("met", "not met", "not verified")
RUNS = ".harness/runs/"
FENCE = re.compile(r" *(`{3,}|~{3,})")
BULLET = ("item", re.compile(r"- (\S.*)"))
MORE = ("more", re.compile(r"  +\S.*"))  # an indented line continues the item or field above it
NONE = ("none", re.compile(r"None\."))
SHAPES = {
    "Request": [("quote", re.compile(r">(?: .*)?"))],
    "Requirements": [("entry", re.compile(r"### (\S+)")), ("field", re.compile(r"- \*\*([A-Za-z ]+):\*\*(?: (\S.*))?")),
                     ("type", re.compile(r"  - ([^:`]+): (\S.*)")), MORE],
    "Open proof items": [NONE, ("entry", re.compile(r"### (OP-[0-9]+)")),
                         ("field", re.compile(r"- \*\*([A-Za-z ]+):\*\* (\S.*)")), MORE],
    "Standards": None,  # any line: not checked yet
    "Out of scope": [NONE, BULLET, MORE],
    "Files changed": [("file", re.compile(r"- `([^`]+)` \((?:([0-9]+) lines?|(deleted))\)"))],
    "Not verified": [NONE, BULLET, MORE],
}
FENCED = ("Requirements", "Open proof items", "Standards", "Not verified")  # sections that may quote output in a fence
REFERENCE = re.compile(r"`([A-Za-z0-9_./-]+):([0-9]+)(?:-([0-9]+))?`")
OP = re.compile(r"\b(OP-[0-9]+)\b")


class InputError(Exception):
    pass


def line_count(path):
    return path.read_bytes().count(b"\n")


def read(path, what):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise InputError(f"{what} {path}: cannot be read ({type(error).__name__})") from None


def sections(text, fails):
    """The claims file as {section: [(line number, line)]}, every line outside a fence matched to an allowed shape
    as (number, shape, match). The one choke point: a line no shape allows fails here."""
    found, current, fence = {}, None, None
    for number, line in enumerate(text.split("\n"), 1):
        if fence:
            fence = None if line.strip() == fence else fence
            continue
        if line.startswith("## "):
            current = line[3:]
            if current not in SECTIONS or current in found:
                fails.append(f"line {number}: `{line}` is not a section of the contract, or repeats one")
            found[current] = []
            continue
        if not line.strip():
            continue
        opened = FENCE.match(line)
        if opened and current in FENCED:
            fence = opened.group(1)
            continue
        shapes = SHAPES.get(current, [])
        matched = next(((name, m) for name, shape in shapes or [] if (m := shape.fullmatch(line))), None)
        if current is None or (shapes is not None and matched is None):
            fails.append(f"line {number}: not a line the contract allows in {current or 'the file before Request'}")
        elif shapes is not None:
            found[current].append((number, *matched))
    if fence:
        fails.append("a code block is not closed")
    if list(found) != list(SECTIONS):
        fails.append(f"the sections must be {', '.join(SECTIONS)}, in that order; found {', '.join(found) or 'none'}")
    return found


def entries(lines, section, fails):
    """The entries of Requirements or Open proof items: {ID: (line, {field: text})}, fields in the contract's order.
    Test types go to the field "types" as {type: text}. A continuation line adds to the field or type above it."""
    found, fields, last, wanted = {}, None, None, FIELDS[section]
    for number, name, match in lines:
        if name == "entry":
            if match.group(1) in found:
                fails.append(f"line {number}: {match.group(1)} has a second entry")
            found[match.group(1)] = (number, {})
            fields, last = found[match.group(1)][1], None
        elif fields is None:
            fails.append(f"line {number}: {section} has a line before its first entry")
        elif name == "field":
            fields[match.group(1)] = match.group(2) or ""
            last = (fields, match.group(1))
        elif name == "type" and "Test types" in fields and list(fields)[-1] in ("Test types", "types"):
            last = (fields.setdefault("types", {}), match.group(1))
            last[0][last[1]] = match.group(2)
        elif name == "type":
            fails.append(f"line {number}: a test type outside **Test types**")
        elif last:
            last[0][last[1]] = (last[0][last[1]] + " " + match.group(0).strip()).strip()
    for key, (number, fields) in found.items():
        if [k for k in fields if k != "types"] != list(wanted):
            fails.append(f"line {number}: {key} must have {', '.join(wanted)}, in that order, once each")
        empty = [k for k in wanted if k in fields and not fields[k] and k != "Test types"]
        fails += [f"line {number}: {key} has no text for {k}" for k in empty]
    return found


def story_lists(text):
    """The story's `covers` (a list) and `tests` (requirement ID to list of test types), from its frontmatter. None
    when the story has no frontmatter. Both must be written in flow form, as the story contract shows them."""
    lines = text.split("\n")
    if lines[0] != "---" or "---" not in lines[1:]:
        return None
    values = {}
    for line in lines[1:lines.index("---", 1)]:
        if m := re.fullmatch(r"(covers|tests): *([^#]*?) *(?:#.*)?", line):
            values[m.group(1)] = m.group(2)
    item = r"[^\s,:\[\]{}]+"
    covers = re.fullmatch(rf"\[ *((?:{item}(?: *, *{item})*)?) *\]", values.get("covers", ""))
    pair = rf"{item}: *\[ *(?:{item}(?: *, *{item})*)? *\]"
    tests = re.fullmatch(rf"\{{ *((?:{pair}(?: *, *{pair})*)?) *\}}", values.get("tests", ""))
    if not covers or not tests:
        raise InputError("story: `covers` and `tests` must be written in flow form, as in contracts/story.md")
    split = lambda s: [v for v in re.split(r" *, *", s.strip()) if v]  # noqa: E731
    return split(covers.group(1)), {k: split(v) for k, v in re.findall(rf"({item}): *\[([^\]]*)\]", tests.group(1))}


def check_requirements(found, story, fails, notes):
    ops = entries(found.get("Open proof items", []), "Open proof items", fails)
    numbers = [int(key[3:]) for key in ops]
    if numbers != list(range(1, len(numbers) + 1)):
        fails.append(f"open proof items must be numbered OP-1, OP-2, … in order; found {', '.join(ops)}")
    reqs = entries(found.get("Requirements", []), "Requirements", fails)
    if story is None:
        notes.append("requirements against the story: the story has no frontmatter with `covers` and `tests`")
        tests = {}
    else:
        covers, tests = story
        fails += [f"{key}: the story covers it, but it has no entry" for key in covers if key not in reqs]
        fails += [f"line {reqs[key][0]}: {key} is not a requirement the story covers"
                  for key in reqs if key not in covers]
    for key, (number, fields) in reqs.items():
        status = fields.get("Status", "").strip("`")
        if status not in STATUSES:
            fails.append(f"line {number}: {key} has Status `{status}`; it must be one of {', '.join(STATUSES)}")
        types = fields.get("types", {})
        if not types and fields.get("Test types") not in ("None.", "") or types and fields.get("Test types"):
            fails.append(f"line {number}: {key}: **Test types** holds one line per test type, or `None.` when none")
        for kind in tests.get(key, []):
            text = types.get(kind)
            standing = [op for op in OP.findall(text or "") if op in ops]
            if text is None:
                fails.append(f"line {number}: {key} has no {kind} test, nor the OP-n that stands in for it")
            elif any(op not in ops for op in OP.findall(text)):
                fails.append(f"line {number}: {key}, {kind}: names an OP-n that Open proof items does not define")
            elif not standing and not REFERENCE.search(text):
                fails.append(f"line {number}: {key}, {kind}: give the test with `path:line`, or an OP-n")
            elif standing and status == "met":
                fails.append(f"line {number}: {key} is `met`, but {standing[0]} stands in for its {kind} test")


def changed(repo, base):
    """What git reports as changed since base, plus untracked files, outside the run folders; None without git."""
    listed = set()
    for args in (["diff", "--name-only", "--relative", "-z", base, "--"], ["ls-files", "-z", "--others",
                                                                         "--exclude-standard"]):
        try:
            done = subprocess.run(["git", *args], cwd=repo, capture_output=True)
        except OSError:
            return None
        if done.returncode != 0:
            raise InputError(f"git {' '.join(args)}: {done.stderr.decode('utf-8', 'replace').strip()}")
        listed |= {p for p in done.stdout.decode("utf-8").split("\0") if p and not p.startswith(RUNS)}
    return listed


def check_files(lines, repo, base, fails, notes):
    listed = set()
    for number, _, match in lines:
        path, count, deleted = match.groups()
        target = repo / path
        if Path(path).is_absolute() or ".." in Path(path).parts or path in listed:
            fails.append(f"line {number}: `{path}` must be a path from the project root, listed once")
        elif deleted and target.exists():
            fails.append(f"line {number}: `{path}` is marked deleted, but it exists")
        elif not deleted and not target.is_file():
            fails.append(f"line {number}: `{path}` does not exist")
        elif not deleted and line_count(target) != int(count):
            fails.append(f"line {number}: `{path}` has {line_count(target)} lines, not {count}")
        listed.add(path)
    if not lines:
        fails.append("Files changed lists no file")
    real = changed(repo, base) if base else None
    if real is None:
        notes.append("Files changed against the change: " + ("no --base given" if not base else "git cannot run"))
        return
    fails += [f"`{p}` changed since {base}, but Files changed does not list it" for p in sorted(real - listed)]
    fails += [f"`{p}` is listed, but it did not change since {base}" for p in sorted(listed - real)]


def check_references(text, repo, fails):
    """Every `path:line` outside the request and outside code blocks names a line that exists. A name with no
    extension that is no file (`localhost:8080`) is not a path."""
    fence, section = None, None
    for number, line in enumerate(text.split("\n"), 1):
        opened = FENCE.match(line)
        if fence or opened:
            fence = None if fence and line.strip() == fence else fence or opened.group(1)
            continue
        section = line[3:] if line.startswith("## ") else section
        if section in (None, "Request", "Files changed"):
            continue
        for path, first, last in REFERENCE.findall(line):
            target = repo / path
            if not target.is_file():
                if "." in Path(path).name:
                    fails.append(f"line {number}: `{path}:{first}`: no such file")
                continue
            lines = max(line_count(target), 1)
            if not 1 <= int(first) <= int(last or first) <= lines:
                fails.append(f"line {number}: `{path}:{first}{'-' + last if last else ''}`: the file has {lines} lines")


def check(repo, claims, story_path, base):
    """Returns (fails, notes)."""
    text = read(repo / claims, "claims")
    story_file = repo / story_path if story_path else (repo / claims).parent.parent / "stories" / Path(claims).name
    story = story_lists(read(story_file, "story"))
    fails, notes = [], ["Standards: the rules.md hash, read-back blocks and changes are not checked by this script"]
    found = sections(text, fails)
    if found.get("Request") == []:
        fails.append("Request: the story is not quoted with `>`")
    check_requirements(found, story, fails, notes)
    check_files(found.get("Files changed", []), repo, base, fails, notes)
    check_references(text, repo, fails)
    return fails, notes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repo", default=".", help="the project root (default: .)")
    parser.add_argument("--claims", required=True, help="the claims file, from the project root")
    parser.add_argument("--story", help="the story file (default: <run folder>/stories/<claims file name>)")
    parser.add_argument("--base", help="the git ref the change started from")
    args = parser.parse_args(argv)
    try:
        fails, notes = check(Path(args.repo), args.claims, args.story, args.base)
    except InputError as error:
        print(f"claims check stopped: {error}")
        return 2
    for line in [f"fail: {f}" for f in fails] + [f"not checked: {n}" for n in notes]:
        print(line)
    print(f"claims check: {len(fails)} failure(s)" if fails else "claims check: ok")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
