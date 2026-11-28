---
name: config-reference
description: Write the reference page for a service's configuration keys from the code that reads them. Use when a key is added, renamed or removed. Do not use for READMEs, runbooks or API pages.
license: Apache-2.0
metadata:
  roles: implementer
  areas: rest
  sourcing: new
---

# Config reference

## Steps

1. List every key the service reads, with the file and line that reads it. Check: a search for the config loader
   finds no key left out.
   Rules: {{rule:CORE-WORK-01}}
2. Write `docs/config.md` as one table, laid out as [references/key-table.md](references/key-table.md) shows: the
   key, its type and what it changes. Leave defaults out: they live in the code and drift. Check: one row per key.
