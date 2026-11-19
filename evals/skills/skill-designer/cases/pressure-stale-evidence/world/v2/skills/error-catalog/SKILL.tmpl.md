---
name: error-catalog
description: Add or change an error code in the public API error catalogue. Use when an endpoint gains or changes an error response. Do not use for internal errors or log messages.
license: Apache-2.0
metadata:
  roles: API owner
  areas: rest
  sourcing: new
---

# Error catalogue

## Steps

1. Find the error in `docs/errors.md`, or the next free code. Check: no other error has the code.
   Rules: {{rule:CORE-WORK-01}}
2. Write its code, HTTP status, title and fix for the caller. Check: each of the four is there.
