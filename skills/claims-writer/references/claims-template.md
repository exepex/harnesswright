# Claims template

The layout of a claims file, as the claims contract in [06 · Contracts](../../../docs/design/06-contracts.md)
defines it. Copy it, keep the six headings exactly, and replace every part in angle brackets.

```markdown
# Claims · <story id>

## Request

> <the story, quoted line by line, including its acceptance criteria>

## Requirements

### AC-1 · <the criterion, in a few words>
- **Status:** <met | not met | not verified>
- **Done:** <what changed, with `path:line` or `path:first-last`>
- **Evidence:** <test names with `path:line`; the command run, its exit code and the output lines that prove it, in backticks or a code block>

### AC-2 · <…>
- **Status:** …
- **Done:** …
- **Evidence:** …

## Standards

- <rule ID>: <how it was applied; any exception and its reason>

## Out of scope

- <what the change deliberately does not do>: <reason>

## Files changed

- `<path>` (<N> lines)
- `<path>` (deleted)

## Not verified

- <what could not be proven>: <why, and what would prove it>
```

Notes:

- Write `None.` in a section that has nothing to say. The check rejects an empty section.
- Put `file:line` references in backticks, such as `` `src/pricing.py:18` `` or `` `Makefile:3` ``, so the check
  can confirm the line exists. Paths are relative to the project root, the folder that holds `.harness/`.
- Give each criterion its own `### AC-n` entry with exactly one **Status**: `met`, `not met` or `not verified`.
- Quote command output exactly. Shorten long output with `…`, but keep the lines with the counts and the result.
- A criterion is `not verified` when its evidence could not be produced here, and `not met` when the evidence
  shows it fails.
