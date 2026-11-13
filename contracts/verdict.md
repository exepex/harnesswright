---
subject: <subject>          # a story ID, or feature
commit: <commit>            # the exact commit judged
rules: <hash>               # hash of the rules.md the judge read
result: <result>            # pass | fail
votes: {approve: <N>, reject: <N>}
blockers: []                # confirmed blockers, by finding ID; any entry forces fail
---

## Claims

### <requirement ID>

- **Result:** <result>  <!-- checked | refuted -->
- **Evidence:** <what the judge ran or read, and what it showed>

## Approvals

- <item ID>: <approval>  <!-- a link to the review or comment | not approved | not verified -->

## Standards

### Skills run

#### <skill name>

- **Version:** <skill version>
- **SKILL.md:** <hash of the release SKILL.md>
- **Rules text:** <status>  <!-- verified | not verified -->

```text
<the read-back block of its rules text, quoted exactly>
```

### Changes applied

- <rule ID> · <rule title, quoted exactly>

## To pass

- <what must change for a pass>
