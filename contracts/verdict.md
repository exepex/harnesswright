---
subject: <subject>          # a story ID, or feature
commit: <commit>            # the exact commit judged
rules: <hash>               # hash of the rules.md the judge read
result: <result>            # pass | fail
votes: {approve: <N>, reject: <N>}
blockers: [<finding ID>]    # confirmed blockers; [] when none
---

## Claims

### <claim>  <!-- a requirement ID, an OP-n or a claims section -->

- **Result:** <result>  <!-- checked | refuted -->
- **Evidence:** <what the judge ran or read, and what it showed>

## Approvals

<!-- item ID form: AC-1, NFR-2, or with its story ID for a waiver or an open proof item, S02 OP-1 -->
- <item ID>: <approval>  <!-- a link to the review or comment | not approved | not verified -->

## Standards

### Skills run

#### <skill name>  <!-- in the order run -->

- **Version:** <skill version>
- **SKILL.md:** <hash of the release SKILL.md>
- **Rules text:** not verified  <!-- only when the rules text was written by reading -->

```text
<each read-back block of its rules text, markers included, in file order, quoted exactly>
```

### Changes applied

- <the ID as the rules text writes it> · <its title, quoted exactly>

## To pass

- <what must change for a pass>
