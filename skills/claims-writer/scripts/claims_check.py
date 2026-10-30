#!/usr/bin/env python3
"""Line counts for the claims contract, and a structure check of a finished claims file.

Usage:
  python3 claims_check.py lines [--repo DIR] [--base REF] [PATH ...]
  python3 claims_check.py check [--repo DIR] [--story STORY_FILE] [--base REF] CLAIMS_FILE

`lines` prints one Markdown list item per changed file, "- `path` (N lines)" or "- `path` (deleted)".
It takes the paths given, or, with --base, every file git reports as changed since REF, plus untracked
files. Paths under .harness/runs/ are left out: the run folder is not part of the change.

`check` exits 0 when the claims file has the six contract sections in order, quotes the request, has one
entry under Requirements for each acceptance criterion of the story and no other, gives each entry a valid
Status, lists each changed file with its true line count, points every `file:line` reference at a line that
exists, and makes no unproven success claim. With --base it also checks that Files changed lists exactly
the files git reports as changed. It prints each problem found and exits 1 otherwise. The story is
--story, or else ../stories/<same name> next to the claims folder; without one, AC mapping is skipped
with a note. All paths are relative to --repo, the project root that holds .harness/.

A line count is the number of newline characters in the file, the same as `wc -l`.
Python 3 standard library only, no network calls, deterministic.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

SECTIONS = ("Request", "Requirements", "Standards", "Out of scope", "Files changed", "Not verified")
RUN_FOLDER = ".harness/runs/"
FILE_ENTRY = re.compile(r"^\s*[-*]\s+`([^`]+)`\s+\((\d+) lines?\)|^\s*[-*]\s+`([^`]+)`\s+\(deleted\)")
# A `path:line` reference. Paths without an extension (`Makefile:3`) are checked when the file exists, so
# a value such as `localhost:8080` is not mistaken for a missing file.
FILE_REF = re.compile(r"`([A-Za-z0-9_./-]+):(\d+)(?:-(\d+))?`")
AC_ID = re.compile(r"\bAC-(\d+)\b")
STATUS = re.compile(r"^\s*[-*]\s+\*\*Status:\*\*\s*(.*?)\s*$", re.MULTILINE)
STATUSES = ("met", "not met", "not verified")
HEDGES = ("should work", "should pass", "should be fine", "probably", "seems to", "looks correct",
          "looks good", "i think it")


def line_count(path):
    return Path(path).read_bytes().count(b"\n")


def _git(repo, *args):
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return [line for line in done.stdout.splitlines() if line]


def changed_paths(repo, base):
    paths = set(_git(repo, "diff", "--name-only", base, "--"))
    paths |= set(_git(repo, "ls-files", "--others", "--exclude-standard"))
    return sorted(p for p in paths if not p.startswith(RUN_FOLDER))


def cmd_lines(args):
    repo = Path(args.repo)
    paths = sorted(set(args.paths) | set(changed_paths(repo, args.base) if args.base else []))
    if not paths:
        print("no paths given and no --base; nothing to count", file=sys.stderr)
        return 2
    for path in paths:
        target = repo / path
        print(f"- `{path}` ({line_count(target)} lines)" if target.is_file() else f"- `{path}` (deleted)")
    return 0


def split_sections(text):
    """Return [(heading, body)] for each level-2 heading, in order."""
    sections, heading, body = [], None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(body).strip()))
            heading, body = line[3:].strip(), []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(body).strip()))
    return sections


def check_files(body, repo):
    problems, entries = [], 0
    for line in body.splitlines():
        match = FILE_ENTRY.match(line)
        if not match:
            continue
        entries += 1
        if match.group(3):
            if (repo / match.group(3)).exists():
                problems.append(f"Files changed: {match.group(3)} is marked deleted but exists")
            continue
        path, stated = match.group(1), int(match.group(2))
        target = repo / path
        if not target.is_file():
            problems.append(f"Files changed: {path} does not exist")
        elif line_count(target) != stated:
            problems.append(f"Files changed: {path} has {line_count(target)} lines, claims say {stated}")
    if entries == 0:
        problems.append("Files changed: no entry of the form - `path` (N lines)")
    return problems


def check_refs(text, repo):
    problems = []
    for path, first, last in FILE_REF.findall(text):
        target = repo / path
        if not target.is_file():
            if "." in Path(path).name:
                problems.append(f"reference `{path}:{first}`: file not found")
            continue
        lines = max(line_count(target), 1)
        if int(last or first) > lines or int(first) < 1:
            problems.append(f"reference `{path}:{first}{'-' + last if last else ''}`: file has {lines} lines")
    return problems


def story_criteria(story_text):
    """AC IDs in the story's acceptance criteria section, or in the whole story if it has none."""
    match = re.search(r"^##\s+Acceptance criteria\s*$(.*?)(?=^##\s|\Z)", story_text, re.MULTILINE | re.DOTALL)
    return sorted(set(AC_ID.findall(match.group(1) if match else story_text)), key=int)


def check_requirements(body, story_text):
    """Each requirement entry (a ### heading) names one AC and has a valid Status; every AC is covered."""
    problems, claimed = [], []
    entries = re.split(r"^###\s+", body, flags=re.MULTILINE)[1:]
    if not entries:
        return ["Requirements: no entry headed '### AC-n'"]
    for entry in entries:
        heading = entry.splitlines()[0].strip()
        ids = AC_ID.findall(heading)
        if len(ids) != 1:
            problems.append(f"Requirements: entry '{heading}' must name exactly one AC-n")
        claimed += ids
        statuses = STATUS.findall(entry)
        if len(statuses) != 1:
            problems.append(f"Requirements: entry '{heading}' needs exactly one **Status:** line")
        elif statuses[0].strip("`*_ ").lower() not in STATUSES:
            problems.append(f"Requirements: entry '{heading}' has Status '{statuses[0]}'; "
                            f"use one of {', '.join(STATUSES)}")
    for ac in sorted({a for a in claimed if claimed.count(a) > 1}, key=int):
        problems.append(f"Requirements: AC-{ac} has more than one entry")
    if story_text is not None:
        wanted = story_criteria(story_text)
        problems += [f"Requirements: AC-{a} of the story has no entry" for a in wanted if a not in claimed]
        problems += [f"Requirements: AC-{a} is not in the story" for a in sorted(set(claimed) - set(wanted), key=int)]
    return problems


def check_diff(body, repo, base):
    listed = set()
    for line in body.splitlines():
        match = FILE_ENTRY.match(line)
        if match:
            listed.add(match.group(1) or match.group(3))
    changed = set(changed_paths(repo, base))
    return ([f"Files changed: {p} changed since {base} but is not listed" for p in sorted(changed - listed)] +
            [f"Files changed: {p} is listed but did not change since {base}" for p in sorted(listed - changed)])


def find_story(claims, story):
    if story:
        return Path(story)
    guess = claims.parent.parent / "stories" / claims.name
    return guess if claims.parent.name == "claims" and guess.is_file() else None


def cmd_check(args):
    repo, claims = Path(args.repo), Path(args.claims)
    text = claims.read_text(encoding="utf-8")
    sections = split_sections(text)
    found = [heading for heading, _ in sections]
    problems = []
    if [h for h in found if h in SECTIONS] != list(SECTIONS):
        problems.append(f"sections must be {', '.join(SECTIONS)} in that order; found {', '.join(found)}")
    bodies = dict(sections)
    for heading in SECTIONS:
        if heading in bodies and not bodies[heading]:
            problems.append(f"{heading}: section is empty; write 'None.' when there is nothing")
    if "Request" in bodies and not any(l.startswith(">") for l in bodies["Request"].splitlines()):
        problems.append("Request: the story is not quoted (no line starts with '>')")
    story = find_story(claims, args.story)
    if story is None:
        print("note: no story file found, so acceptance criteria were not matched; pass --story")
    if "Requirements" in bodies:
        story_text = story.read_text(encoding="utf-8") if story else None
        problems += check_requirements(bodies["Requirements"], story_text)
    if "Files changed" in bodies:
        problems += check_files(bodies["Files changed"], repo)
        if args.base:
            problems += check_diff(bodies["Files changed"], repo, args.base)
    problems += check_refs(text, repo)
    # The quoted request is the story's own text, so only the implementer's sections are searched.
    lowered = "\n".join(body for heading, body in sections if heading != "Request").lower()
    problems += [f"unproven success wording: '{h}'" for h in HEDGES if h in lowered]
    for problem in problems:
        print(problem)
    print("claims check: ok" if not problems else f"claims check: {len(problems)} problem(s)")
    return 0 if not problems else 1


def main(argv=None):
    top = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = top.add_subparsers(dest="command", required=True)
    lines = sub.add_parser("lines")
    lines.add_argument("--repo", default=".")
    lines.add_argument("--base", help="git ref the change started from")
    lines.add_argument("paths", nargs="*")
    lines.set_defaults(func=cmd_lines)
    check = sub.add_parser("check")
    check.add_argument("--repo", default=".")
    check.add_argument("--story", help="the story file (default: ../stories/<claims file name>)")
    check.add_argument("--base", help="git ref the change started from; Files changed must match the diff")
    check.add_argument("claims")
    check.set_defaults(func=cmd_check)
    args = top.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
