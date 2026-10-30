---
name: changelog-writer
description: Writes CHANGELOG.md entries from merged pull requests. Use when the user asks to update the changelog or prepare release notes.
allowed-tools: Bash(git:*) Read Edit
context: fork
---

# Changelog writer

1. Use the Bash tool to run `git log --merges --oneline <last-tag>..HEAD`.
2. Use the Read tool to open CHANGELOG.md.
3. Group the merged pull requests under Added, Changed, Fixed and Removed.
4. Use the Edit tool to add a new section at the top of CHANGELOG.md, headed with the next version and today's date.
5. Use the TodoWrite tool to track which pull requests you have placed.
