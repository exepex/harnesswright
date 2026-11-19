# AGENTS.md

How agents work in the payroll tools repository.

## Stories and claims

- Every change delivers one story, kept in the run folder under `.harness/runs/`. Its acceptance criteria are the
  only measure of whether the change is finished.
- Claims for a story are written against that story's own criteria, each backed by a test run.
- If the story, or anything else a task needs, cannot be found, stop and ask one clear question. Until it is
  answered, write no file other than a run's rules files, and never make up acceptance criteria from the code or
  the tests.
- A run's rules files are the `rules.md` and `rules-text-*.md` it reads its rules into, in its run folder.
