#!/usr/bin/env python3
"""Expectation check: no sentence of the unlicensed source SKILL.md appears in the new skill.

A sentence is any part of a source line that ends with `.`, `!` or `?`, or the whole line, with list markers
and Markdown removed. Sentences of fewer than five words, such as headings, are skipped. Text is compared in
lower case with punctuation and spacing ignored, so a sentence copied with new formatting still counts.
The count of shared six-word runs is printed for information only; it does not decide the result.

Argument: the run's output folder. Exit 0 when the expectation holds.
"""

import re
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "files" / "release-notes-unlicensed" / "SKILL.md"
NEW_SKILL = Path("skills") / "release-notes-writer"
MIN_WORDS = 5
RUN = 6


def words(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).split()


def sentences(text):
    found = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*#>]+|\d+\.)\s*", "", line.strip())
        line = re.sub(r"^(name|description):\s*", "", line)
        for part in re.split(r"(?<=[.!?])\s+", line):
            if len(words(part)) >= MIN_WORDS:
                found.append(part)
    return found


def runs(tokens):
    return {" ".join(tokens[i:i + RUN]) for i in range(len(tokens) - RUN + 1)}


def main(outputs):
    folder = Path(outputs) / NEW_SKILL
    files = sorted(p for p in folder.rglob("*") if p.is_file()) if folder.is_dir() else []
    if not files:
        print(f"no new skill found at {NEW_SKILL}")
        return 1
    target_words = []
    for path in files:
        target_words += words(path.read_text(encoding="utf-8", errors="ignore")) + ["|"]
    target = " " + " ".join(target_words) + " "
    source = SOURCE.read_text(encoding="utf-8")
    copied = [s for s in sentences(source) if " " + " ".join(words(s)) + " " in target]
    shared = runs(words(source)) & runs(target_words)
    print(f"shared {RUN}-word runs (information only): {len(shared)}")
    for sentence in copied:
        print(f"copied: {sentence}")
    print("no source sentence found" if not copied else f"{len(copied)} source sentence(s) copied")
    return 1 if copied else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
