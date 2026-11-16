---
name: pr-helper
description: Drafts a pull request description from the branch. Use whenever someone opens a PR or asks for a PR write-up.
---

# PR helper

Turn the work on the current branch into a description a reviewer can take in within a couple of minutes.

## Before you write

1. Find where the branch left main and list every commit since then, oldest first.
2. List the files the branch touches, grouped by top-level folder.
3. Look for a linked issue in the branch name or the commit messages, and read it if there is one.
4. If the branch mixes two unrelated changes, tell the author and suggest splitting it before you write anything.

## Writing it

5. Start with a title in the imperative mood that would still make sense in the release notes.
6. Open the body with one or two sentences on the problem this change solves, in the words a user would use.
7. Under **What changed**, write one bullet for each area of the code, not one for each commit.
8. Call out anything a reviewer could easily miss, such as a renamed setting or a changed default.
9. Under **How to test**, give the exact commands to run and what a passing result looks like.
10. Under **Risk**, mention anything that touches stored data, logins or a public API. If nothing does, write "Low".
11. Add screenshots only when the change alters something people see on screen.
12. Link the issue at the end with a closing keyword, so that it closes when the pull request merges.

## Before you post

13. Read it once as the reviewer would, cut anything that only repeats the diff, and keep it under 300 words.
