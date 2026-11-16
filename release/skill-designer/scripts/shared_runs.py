#!/usr/bin/env python3
"""Find runs of words that a written file shares with a source.

Run from the project root:
  python3 shared_runs.py --source PATH [--source PATH ...] --written PATH [--written PATH ...] [--words N]

A source or written path may be a file or a folder (every file under it). A word is a run of letters and digits,
compared without case; everything else, white space, punctuation and Markdown marks, only separates words, so a run
split by a comma or a line break is still found. A file is read as the text a person sees: a `.json` file that parses
is read as its keys and string values, with every escape decoded, so `\\n` or `\\u2014` never joins or splits a
word. N is 8 unless given.

Standard library only, no network, deterministic. Exit 0: no written file shares N words in a row with a source.
Exit 1: each "shared:" line names a written file, a source file and the run, longest first. Exit 2: a path is
missing or cannot be read.
"""

import argparse
import json
import re
import sys
from pathlib import Path

WORD = re.compile(r"[^\W_]+")


def files(path):
    """The files of `path`: itself, or every file under it, in order."""
    path = Path(path)
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(p for p in path.rglob("*") if p.is_file())
    raise OSError(f"{path}: no such file or folder")


def words(path):
    """The words of `path` as a person reads it (see the module's docstring), in order, lower case."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if Path(path).suffix == ".json":
        try:
            text = "\n".join(_strings(json.loads(text)))
        except ValueError:
            pass  # not JSON after all: read as written
    return [w.lower() for w in WORD.findall(text)]


def _strings(value):
    """Every key and string of a parsed JSON value, in order."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def shared(written, source, n):
    """The longest runs of at least `n` words that `written` (a word list) shares with `source`, each once."""
    starts = {}
    for i in range(len(source) - n + 1):
        starts.setdefault(tuple(source[i:i + n]), []).append(i)
    found, i = [], 0
    while i <= len(written) - n:
        hits = starts.get(tuple(written[i:i + n]))
        if not hits:
            i += 1
            continue
        best = max(_length(written, i, source, j) for j in hits)
        found.append(" ".join(written[i:i + best]))
        i += best
    return sorted(set(found), key=lambda run: (-len(run.split()), run))


def _length(a, i, b, j):
    k = 0
    while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
        k += 1
    return k


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--written", action="append", required=True)
    parser.add_argument("--words", type=int, default=8)
    args = parser.parse_args(argv)
    if args.words < 1:
        print("error: --words must be at least 1")
        return 2
    try:
        sources = [(p, words(p)) for given in args.source for p in files(given)]
        written = [(p, words(p)) for given in args.written for p in files(given)]
    except OSError as error:
        print(f"error: {error}")
        return 2
    lines = [f"shared: {w} with {s}: {run}" for w, ws in written for s, ss in sources
             for run in shared(ws, ss, args.words)]
    print("\n".join(lines) if lines else f"no written file shares {args.words} words in a row with a source")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main())
