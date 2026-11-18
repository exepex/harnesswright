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

1. Read the diff against the base branch. Check: every changed file is accounted for.
   Rules: {{rule:CORE-WORK-01}}
2. Write what changed and why, one bullet per area. Check: no bullet repeats a commit subject.
   Rules: {{rule:CORE-SKILL-05}}
3. Replace the pull request's description. Check: the description names how a reviewer can try the change.
