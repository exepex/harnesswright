---
name: release-notes
description: Turns the commits since the last tag into short, user-facing release notes. Use when asked for release notes or a summary of what shipped.
---

# Release notes

1. Run `scripts/collect.sh` to list the commits since the last tag.
2. Drop commits that only touch tests, CI or formatting.
3. Rewrite each remaining commit as one sentence a user would understand, starting with a verb.
4. Put breaking changes first, under a "Breaking" heading.
5. Print the notes as Markdown.
