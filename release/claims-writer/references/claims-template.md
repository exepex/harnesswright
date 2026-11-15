<!-- Generated from v2/skills/claims-writer/references/claims-template.md at version 0.3.4. Do not edit. -->

# Claims layout

The layout of a claims file, `<run folder>/claims/<story ID>.md`. It is the claims contract,
`contracts/claims.md` in the harnesswright repository, unchanged, between the two `~~~~` lines below.

How to fill it:

- Keep every heading and field. Replace each part in angle brackets.
- A comment gives the allowed values, the order of entries, or when a part applies (`only when`). Delete the
  comments as you fill the file, and leave out a line marked `only when` when its condition does not hold.
- Repeat an entry, such as `### AC-1`, once per item, under the item's own ID.
- Write `None.` in a section that has nothing in it.

~~~~markdown
## Request

> <the story, quoted line by line>

## Requirements

### <requirement ID>

- **Status:** <met | not met | not verified>
- **Done:** <what was done, with `path:line`>
- **Evidence:** <test names with `path:line`; the command run and the output lines that prove it>
- **Test types:**
  - <test type>: <the test that proves it, with `path:line`, or the `OP-n` that stands in for it>

## Open proof items

### OP-1

- **Unproven:** <what is unproven, with its requirement ID and test type if it stands in for a test>
- **Proof:** <where and when the proof will come from>
- **Owner:** <who owns it>

## Standards

- **rules.md:** <hash of rules.md>

### Skills run

#### <skill name>  <!-- in the order run -->

- **Source:** <this run | log>
- **Version:** <skill version>
- **SKILL.md:** <hash of the release SKILL.md>
- **Rules text:** not verified  <!-- only when the rules text was written by reading -->

<!-- one fence per rules text read, in the stack order of rules.md -->
```text
<the read-back block of one rules text, markers and Stack line included, quoted exactly>
```

### Changes applied

- <the ID and title that start the change's line in the rules text, quoted exactly>  <!-- once per change -->

### Rules applied

- <rule ID> (<this run | log>)

### Waivers used

- <rule ID> (<this run | log>)

## Out of scope

- <what the change does not do>: <reason>

## Files changed

- `<path>` (<N> lines)  <!-- or (deleted) for a deleted file -->

## Not verified

- <what could not be proven>: <why>
~~~~
