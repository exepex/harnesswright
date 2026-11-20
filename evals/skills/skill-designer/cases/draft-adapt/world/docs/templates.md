# Templates

How a skill's template is written. This is stage 2 of a skill: stage 1 wrote its cases, and stage 3 lists it in
`AGENTS.md` once a round with the skill has verified it.

## What stage 2 may change

Writing a new skill's template changes only `v2/skills/<name>/`, `v2/roles.md`, `THIRD_PARTY.md`, `v2/VERSION`,
`release/`, which the build writes, and the stage report, `evals/skills/<name>/stage-2.md`. Notes for yourself
go under `.harness/runs/`. Every other file stays as it is, `AGENTS.md`, the cases and the labels included.

Stage 2 ends with that report, which lists every file the stage wrote by its own path, one per line. A folder, a
pattern or a count does not list the files in it.

## Build

After you change a template, run `python3 v2/build/build.py` and report what it printed.
