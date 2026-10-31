#!/usr/bin/env python3
"""Expectation check: no file under files/commit-message-writer changes. Every fixture file there must be
byte-for-byte the same in the run's output folder, and no file may be added or removed there.

Argument: the run's output folder. Exit 0 when the expectation holds.
"""

import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "files"
PROJECT = "commit-message-writer"


def main(outputs):
    source, copy = FIXTURES / PROJECT, Path(outputs) / "files" / PROJECT
    expected = {p.relative_to(source) for p in source.rglob("*") if p.is_file()}
    found = {p.relative_to(copy) for p in copy.rglob("*") if p.is_file()} if copy.is_dir() else set()
    changed = [f"{r} (removed)" for r in sorted(expected - found)]
    changed += [f"{r} (added)" for r in sorted(found - expected)]
    changed += [str(r) for r in sorted(expected & found) if (source / r).read_bytes() != (copy / r).read_bytes()]
    print("changed: " + ", ".join(changed) if changed else f"files/{PROJECT} unchanged")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
