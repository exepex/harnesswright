# Round release-notes-2

Host claude-code, 3 runs per case, with the skill and without it.

- Task cases: 6 of 6 passed with the skill, 2 of 6 without it.
- Trigger cases, train split: 7 of 10 should-load cases loaded the skill; 10 of 10 near misses left it alone.
- Trigger cases, test split: 7 of 10 should-load cases loaded the skill; 10 of 10 near misses left it alone. Test
  cases are not named here, so that a change is tuned on the train split only.

The three train cases that should load the skill and missed, in every run:

| Case | Prompt |
|---|---|
| `announce-whats-new` | v3.1 is out, write up what's new for customers |
| `release-page-list` | put together the changes list for the 5.0 release page |
| `since-last-version` | draft the announcement for 2.4, what shipped since 2.3? |

The train near misses ask for a changelog entry for one pull request, a commit message, a blog post about the
team, and a migration guide for one breaking change.

Label: `unsupported` on claude-code, trigger accuracy 0.85 on the test split against the 0.9 floor.
