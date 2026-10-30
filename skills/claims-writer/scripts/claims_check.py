#!/usr/bin/env python3
"""Line counts for the claims contract, and a structure check of a finished claims file.

Usage:
  python3 claims_check.py lines [--repo DIR] [--base REF] [PATH ...]
  python3 claims_check.py check [--repo DIR] CLAIMS_FILE

`lines` prints one Markdown list item per changed file, "- `path` (N lines)" or "- `path` (deleted)".
It takes the paths given, or, with --base, every file git reports as changed since REF, plus untracked
files. Paths under .harness/runs/ are left out: the run folder is not part of the change.

`check` exits 0 when the claims file has the six contract sections in order, quotes the request, lists
each changed file with its true line count, points every `file:line` reference at a line that exists,
and makes no unproven success claim. It prints each problem found and exits 1 otherwise.

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
FILE_REF = re.compile(r"`([A-Za-z0-9_./-]+\.[A-Za-z0-9]+):(\d+)(?:-(\d+))?`")
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
            problems.append(f"reference `{path}:{first}`: file not found")
            continue
        lines = max(line_count(target), 1)
        if int(last or first) > lines or int(first) < 1:
            problems.append(f"reference `{path}:{first}{'-' + last if last else ''}`: file has {lines} lines")
    return problems


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
    if "Files changed" in bodies:
        problems += check_files(bodies["Files changed"], repo)
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
    check.add_argument("claims")
    check.set_defaults(func=cmd_check)
    args = top.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
