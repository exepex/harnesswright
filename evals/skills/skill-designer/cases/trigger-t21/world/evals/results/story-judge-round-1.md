# Round story-judge-1

Host claude-code, 3 runs per case, with the skill and without it.

| Case | With the skill | Without it |
|---|---|---|
| `false-claim` | 0 of 3 | 0 of 3 |
| `all-met` | 3 of 3 | 2 of 3 |

`false-claim` failed in every run: the verdict passed a criterion whose test the claims named but the change did
not hold.

Label: `unsupported` on claude-code, task pass rate 0.5.
