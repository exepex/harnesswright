---
name: api-reference
description: Write the reference page of a service's HTTP API from its OpenAPI file. Use when an endpoint is added or changed. Do not use for READMEs, changelogs or client guides.
metadata:
  roles: implementer
  areas: rest
  sourcing: new
---

# API reference

## Steps

1. Read `openapi.yaml`. Check: you have every path and method.
   Rules: {{rule:CORE-WORK-01}}
2. Write `docs/api.md` with one section per endpoint: its request, its responses and one example. Check: no
   endpoint is missing.
