---
name: commit-message-writer
description: Write the commit message for a staged change. Use before each commit. Do not use for pull request text.
metadata:
  roles: implementer
---

1. Read the staged diff. Check: every changed file is named.
2. Write an imperative subject of at most 60 characters. Check: count it.
3. Write the body: why the change was made. Check: it names the story ID.
