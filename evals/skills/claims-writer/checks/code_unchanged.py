#!/usr/bin/env python3
"""Expectation check: writing claims changed no file of the project. Every fixture file outside
.harness/ must be byte-for-byte the same in the run's output folder.

Argument: the run's output folder. Exit 0 when the expectation holds.
"""

import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "files"


def main(outputs):
    projects = [p for p in sorted(FIXTURES.iterdir()) if (Path(outputs) / "files" / p.name).is_dir()]
    if not projects:
        print("no fixture project found in the output folder")
        return 1
    changed = []
    for project in projects:
        for source in sorted(project.rglob("*")):
            relative = source.relative_to(FIXTURES)
            if not source.is_file() or ".harness" in relative.parts:
                continue
            copy = Path(outputs) / "files" / relative
            if not copy.is_file() or copy.read_bytes() != source.read_bytes():
                changed.append(str(relative))
    print("changed or missing: " + ", ".join(changed) if changed else "project files unchanged")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
