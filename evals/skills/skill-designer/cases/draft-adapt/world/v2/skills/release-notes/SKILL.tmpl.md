---
name: release-notes
description: Write the release notes for a tagged version from the pull requests merged since the last tag. Use when a version is tagged and its notes are due. Do not use for commit messages or changelog fixes.
license: Apache-2.0
metadata:
  roles: release manager
  areas: rest
  sourcing: new
---

# Release notes

## Steps

1. List the pull requests merged since the previous tag. Check: each has a number and a title.
   Rules: {{rule:CORE-WORK-01}}
2. Group them under Added, Changed and Fixed. Check: every pull request is in one group.
   Rules: {{rule:CORE-SKILL-05}}
3. Write `docs/releases/<version>.md`. Check: the file names the version and its date.
