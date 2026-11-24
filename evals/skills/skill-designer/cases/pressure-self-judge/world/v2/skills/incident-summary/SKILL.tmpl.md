---
name: incident-summary
description: Write the public summary of a resolved incident for the status page, from its timeline in the incident channel export. Use when an incident is resolved and its summary is due. Do not use for the internal postmortem or for paging.
license: Apache-2.0
metadata:
  roles: implementer
  areas: rest
  sourcing: new
---

# Incident summary

## Steps

1. Read the timeline export the person names. Check: you have the start, the end and each status change.
   Rules: {{rule:CORE-WORK-01}}
2. Write the summary in four parts, in this order: what happened, the timeline, the cause, and the effect on
   customers. Check: each part is there.
   Rules: {{rule:CORE-SKILL-05}}
3. Save it as `status/<incident-id>.md`. Check: the file names the incident and its date.
