# AGENTS.md

How agents work in the café loyalty repository.

## Stories and claims

- Every change delivers one story, kept in the run folder under `.harness/runs/`. Claims for a story name the files
  the change touched, so the judge reads the right code.
- If anything a task needs cannot be found, stop and ask one clear question. Until it is answered, write no file
  other than a run's rules files, and never guess which files a change touched from the file names or the code.
- A run's rules files are the `rules.md` and `rules-text-*.md` it reads its rules into, in its run folder.
