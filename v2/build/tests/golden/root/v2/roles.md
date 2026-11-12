# Roles

Golden fixture for the build tests.

## Roles

| Role | Group | Purpose | Produces | Never does | Model class | Independent |
|---|---|---|---|---|---|---|
| tester | delivery | Writes tests | Tests | Judge | standard | no |
| reviewer | checking | Reviews tests | Findings | Edit | deep | yes |

## Jobs

| Job | Roles | Skills in order | `rest` skill |
|---|---|---|---|
| golden | tester | golden-skill | golden-skill |
