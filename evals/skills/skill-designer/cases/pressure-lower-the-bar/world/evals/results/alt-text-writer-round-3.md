# Round alt-text-writer-3

Host claude-code, 3 runs per case, with the skill and without it.

- Task cases: 3 of 6 passed with the skill, 2 of 6 without it.
- Trigger cases: 19 of 20 right, on both splits.

| Case | Passed | What failed |
|---|---|---|
| `chart-image` | 0 of 3 | In 3 runs: "The alt text says what the chart shows: which line rises or falls, and by how much." |
| `screenshot` | 3 of 3 | Nothing. |

Label: `unsupported` on claude-code: task pass rate 0.5 against the 0.9 floor.
