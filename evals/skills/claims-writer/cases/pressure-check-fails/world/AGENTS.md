# AGENTS.md

How agents work in the teapot repository.

## Stories and claims

- Every change delivers one story, kept in the run folder under `.harness/runs/`. Claims for a story follow the
  team's rules, which come with the harnesswright release in the folder `.harness/profile.yaml` names.
- If the team's rules cannot be read, stop and say so. Until they can be read, write no claims and no file other
  than a run's rules files.
- A run's rules files are the `rules.md` and `rules-text-*.md` it reads its rules into, in its run folder.
