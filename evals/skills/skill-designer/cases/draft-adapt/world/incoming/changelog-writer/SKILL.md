---
name: changelog-writer
description: Keeps CHANGELOG.md up to date. Use when a pull request is about to merge and the changelog needs its entry.
context: fork
---

# Changelog writer

The wording and layout of an entry are in `references/format.md`; read it before step 3.

1. List the branch's commits with `git log --oneline main..HEAD`.
2. Pick the section: Added for new behaviour, Changed for changed behaviour, Fixed for bug fixes.
3. Add one line under `## Unreleased` in CHANGELOG.md, in the past tense, naming what a user notices rather than
   how the code changed.
4. Link the pull request number at the end of the line, like `(#123)`.
5. Open CHANGELOG.md again and look at the new line.
6. Never let secrets or personal data reach the changelog.
7. Do not report the entry until you have seen it there.
