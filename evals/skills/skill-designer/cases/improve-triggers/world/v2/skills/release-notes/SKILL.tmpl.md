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

1. List the pull requests merged since the previous tag (CORE-WORK-01). Check: each has a number and a title.
2. Group them under Added, Changed and Fixed (CORE-SKILL-05). Check: every pull request is in one group.
3. Write `docs/releases/<version>.md`. Check: the file names the version and its date.
