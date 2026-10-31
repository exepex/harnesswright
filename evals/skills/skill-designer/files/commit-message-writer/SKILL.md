---
name: commit-message-writer
description: Write a commit message for staged changes, in the imperative mood, saying what changed and why, with a subject under 72 characters. Use when asked to write or fix a commit message. Do not use for pull request descriptions or release notes.
license: Apache-2.0
metadata:
  sourcing: new
---

# Commit message writer

An eval fixture: a drafted skill waiting for its judge.

## Steps

1. Read the staged diff. Check: you can name every file it touches.
2. Write a subject in the imperative mood, under 72 characters. Check: count its characters.
3. Write a body that says why the change was made. Check: the body answers "why", not only "what".
