# Quality checklist: evidence for each item

The checklist itself is defined in [10 · Skills](../../../docs/design/10-skills.md); that document wins if the two
ever differ. This file says what evidence proves each item, so the same proof goes into the claims and the judge
can check it.

Use it twice: in step 2, to score a candidate skill for adopt, adapt or write new; and in step 7, to write the
claims for your own skill. An item without evidence is not met.

| # | Item | Evidence that proves it |
|---|---|---|
| 1 | Purpose and limits | `file:line` of the section that says what the skill does and what it does not do. |
| 2 | Triggers | The `description` names concrete phrases or file types and at least one case where it must not trigger; trigger eval accuracy per host. |
| 3 | Inputs | `file:line` of the inputs list, with what to do when each input is missing. |
| 4 | Steps | Numbered steps, each with a check a reader can carry out; `file:line` of each check. |
| 5 | Standards by ID | Every rule the skill applies is cited by an ID that exists; no rule text is repeated. Missing rules are listed as proposals. |
| 6 | Verification | The command, test or check that proves the job was done, and where the skill states it. |
| 7 | Failure handling | `file:line` of what to do when a step fails, and when to stop and ask one clear question. |
| 8 | Output | The contract the output fills, named and linked from [06 · Contracts](../../../docs/design/06-contracts.md). |
| 9 | Examples | At least one good and one bad example, with `file:line`. |
| 10 | Evals | Paths to `triggers.json` (both kinds of query) and `tasks.json` (at least one expectation per task). |
| 11 | Portability | Each `HW-PORT` rule checked as below, and eval results per host within the thresholds. |
| 12 | Size | `wc -l` output: `SKILL.md` under 500 lines; every other file within the limits in `AGENTS.md`. |

## Portability checks

| Rule | How to check |
|---|---|
| `HW-PORT-01` | The frontmatter holds only `name`, `description`, `license`, `compatibility` and `metadata`; `name` matches the folder; `metadata` values are strings. |
| `HW-PORT-02` | Search the body for host tool names; there are none. |
| `HW-PORT-03` | Each step that needs a host feature names the capability; steps without independence have a single-agent fallback; independent steps have none and stop instead. |
| `HW-PORT-04` | Each script uses Python 3 standard library or POSIX `sh`, makes no network call and gives the same output for the same input. |
| `HW-PORT-05` | `AGENTS.md` lists the skill with its path and when to use it. |
| `HW-PORT-06` | The output follows a contract, so results from different hosts compare field by field. |
| `HW-PORT-07` | Every output format is stated; nothing relies on a model guessing. |

## Scoring a candidate

For each candidate in step 2, mark every item `met`, `gap` or `missing`, and note what is host-specific. Adopt
only when all twelve are `met`. Adapt when the gaps can be closed without rewriting most of it. Otherwise, write
new.
