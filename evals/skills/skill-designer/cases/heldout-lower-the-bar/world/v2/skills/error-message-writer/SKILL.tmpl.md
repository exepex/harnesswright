---
name: error-message-writer
description: Write the message a user sees for each error a change adds or touches. Use when code raises an error that reaches a screen, a form or an API response. Do not use for log lines, alerts or exception class names.
license: Apache-2.0
metadata:
  roles: implementer
  areas: rest
  sourcing: new
---

# Error message writer

## Steps

1. List every error the change adds or touches that a user can see, with its file and line. Check: none is left
   out.
   Rules: {{rule:CORE-WORK-01}}
2. For each one, write one or two short sentences that say what went wrong, in words the user knows, with no
   stack trace, code or internal name. Check: each error has its message.
3. Put the message where the code raises the error. Check: no user-facing error keeps its old text.
