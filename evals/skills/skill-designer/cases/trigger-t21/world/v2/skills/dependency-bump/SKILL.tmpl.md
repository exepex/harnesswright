---
name: dependency-bump
description: Raise one dependency to a newer version and fix what the upgrade breaks. Use when a dependency needs a newer version.
metadata:
  roles: implementer
---

1. Read the dependency's release notes between the two versions.
2. Change the version in the build file.
3. Run the tests and fix each failure the upgrade causes.
