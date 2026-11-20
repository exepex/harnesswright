---
name: deprecation-notice
description: Write the public notice that an API endpoint is deprecated, with its replacement and removal date. Use when an endpoint is marked deprecated. Do not use for release notes or error codes.
license: Apache-2.0
metadata:
  roles: implementer
  areas: rest
  sourcing: new
---

# Deprecation notice

## Steps

1. Read the endpoint's entry in `openapi.yaml`. Check: it is marked `deprecated: true`.
   Rules: {{rule:CORE-WORK-01}}
2. Write the notice. Its first sentence names the endpoint and the one that replaces it. Check: both are named.
   Rules: {{rule:CORE-SKILL-05}}
3. Give the removal date and the `Sunset` header date, at least 90 days out, in the form of
   [the Sunset header](references/sunset-header.md). Check: both dates are the same.
4. Save it as `docs/deprecations/<endpoint>.md`. Check: the file names the endpoint.
