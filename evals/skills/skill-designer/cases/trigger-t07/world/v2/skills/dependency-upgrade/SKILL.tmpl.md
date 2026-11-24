---
name: dependency-upgrade
description: Upgrade one dependency and fix what breaks. Do not use for adding a new dependency.
metadata:
  roles: implementer
  areas: rest
---

1. Read the build file and find the dependency.
2. Use the TodoWrite tool to plan each module's change.
3. Bump the version and run the build.
4. Fix each failure, then run the build again.
