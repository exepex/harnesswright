---
name: flag-cleanup
description: Remove a feature flag that is fully rolled out, with its dead branch and its config entry. Use when a flag has been on for every user and the owner wants it gone. Do not use to add a flag, change who sees one, or roll one back.
license: Apache-2.0
metadata:
  roles: implementer
  areas: rest
  sourcing: new
---

# Flag cleanup

## Steps

1. Find every place the code reads the flag, with its file and line. Check: a search for the flag's key finds no
   other place.
   Rules: {{rule:CORE-WORK-01}}
2. Keep the branch the flag turned on and delete the other one. Check: the tests still pass.
3. Delete the flag's entry from the config files. Check: no config file names the key.
