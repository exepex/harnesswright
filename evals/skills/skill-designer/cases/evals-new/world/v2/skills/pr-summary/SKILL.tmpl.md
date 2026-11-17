---
name: pr-summary
description: Write or update the description of an open pull request from its diff and commits. Use when a pull request is opened or its scope changes. Do not use for commit messages or release notes.
license: Apache-2.0
metadata:
  areas: DOC
  roles: implementer
  sourcing: new
---

# Pull request summary

## Steps

1. Read the diff against the base branch (CORE-WORK-01). Check: every changed file is accounted for.
2. Write what changed and why, one bullet per area (CORE-SKILL-05). Check: no bullet repeats a commit subject.
3. Replace the pull request's description. Check: the description names how a reviewer can try the change.
