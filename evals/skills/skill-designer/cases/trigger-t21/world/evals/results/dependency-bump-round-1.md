# Round dependency-bump-1

Host claude-code, 3 runs per case, with the skill and without it.

| Case | With the skill | Without it |
|---|---|---|
| `crosses-major` | 0 of 3 | 0 of 3 |
| `patch-only` | 3 of 3 | 2 of 3 |

`crosses-major` failed in every run: the change moved to a new major version that the build file pins out.

Label: `unsupported` on claude-code, task pass rate 0.5.
