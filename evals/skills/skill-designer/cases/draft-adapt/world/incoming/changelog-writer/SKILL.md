---
name: changelog-writer
description: Keeps CHANGELOG.md up to date. Use when a pull request is about to merge and the changelog needs its entry.
allowed-tools: Bash, Read, Edit
context: fork
---

# Changelog writer

1. Use the Bash tool to list the branch's commits with `git log --oneline main..HEAD`.
2. Pick the section: Added for new behaviour, Changed for changed behaviour, Fixed for bug fixes.
3. Use the Edit tool to add one line under `## Unreleased` in CHANGELOG.md, in the past tense, naming what a user
   notices rather than how the code changed.
4. Link the pull request number at the end of the line, like `(#123)`.
