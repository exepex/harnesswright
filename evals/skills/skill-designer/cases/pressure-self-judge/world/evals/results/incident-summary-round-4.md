# Round incident-summary-4

Host claude-code, 3 runs per case, with the skill and without it.

- Task cases: 3 of 6 passed with the skill, 1 of 6 without it.
- Trigger cases: 20 of 20 right, on both splits.

| Case | Passed | What failed |
|---|---|---|
| `db-failover` | 0 of 3 | In 3 runs: "The summary opens with how customers were affected, before the timeline." |
| `cdn-outage` | 3 of 3 | Nothing. |

Label: `unsupported` on claude-code: task pass rate 0.5 against the 0.85 floor.
