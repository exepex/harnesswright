# Round release-notes-2

Host claude-code, 3 runs per case, with the skill and without it.

- Task cases: 5 of 6 passed with the skill, 2 of 6 without it.
- Trigger cases, test split: 7 of 10 should-load cases loaded the skill; 10 of 10 near misses left it alone.

The three should-load cases that missed, in every run:

| Case | Prompt |
|---|---|
| `announce-whats-new` | v3.1 is out, write up what's new for customers |
| `release-page-list` | put together the changes list for the 5.0 release page |
| `since-last-version` | draft the announcement for 2.4, what shipped since 2.3? |

Label: `unsupported` on claude-code, trigger accuracy 0.85 against the 0.9 floor.
