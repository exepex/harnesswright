---
name: release-blurb
description: Write the short announcement of a release for the team chat, from its changelog entry. Use when a release is tagged. Do not use for the changelog itself, release notes pages or customer emails.
license: Apache-2.0
metadata:
  roles: implementer
  areas: rest
  sourcing: new
---

# Release blurb

## Steps

1. Read the release's changelog entry. Check: you have its version and every item.
   Rules: {{rule:CORE-WORK-01}}
2. Write the announcement in `blurb.md`: one line with the version, then the two or three changes users notice
   most. Check: no item is in it that the entry does not hold.
3. Count its words from the project root with `python3 SKILL_DIR/scripts/count_words.py blurb.md`. `SKILL_DIR` is
   the folder that holds this `SKILL.md`. Check: exit 0, so it is 80 words or fewer. On exit 1, shorten it and
   count again.
