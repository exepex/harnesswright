# error-message-writer, round 2

Ran on claude-code only. Each case ran three times in each arm.

## Task cases

| Case | With the skill | Without it | Failed expectation |
|---|---|---|---|
| `plain-words` | 3 of 3 | 2 of 3 | None with the skill. |
| `retry-hint` | 0 of 3 | 1 of 3 | The message tells the user what they can do next. |

## Trigger cases

All 20 loaded or stayed quiet as they should, in both splits.

## Label

`unsupported` on claude-code. The task pass rate with the skill is 50%, under the 90% floor.
