# Evals

How a skill in this toolkit is measured, and who does each part. Every skill goes through it, new or borrowed.

## Order of the work

A skill is made in three stages, each its own piece of work with its own owner:

1. Cases. Nobody writes the skill's `SKILL.tmpl.md` until its cases have goldens and a baseline round without the
   skill has run.
2. The template, under `v2/skills/<name>/`, once the baseline label is in `evals/results/`.
3. A line for the skill in the `AGENTS.md` Skills table, once a round with the skill has verified it.

Each stage ends with a report at `evals/skills/<name>/stage-<n>.md`, where `<n>` is the stage's number, that
lists every file the stage wrote. Whoever takes the next stage starts from that report.

## Cases

Cases go under `evals/skills/<name>/cases/`, one folder per case, each with a `case.json` and a `world/` folder.
Each world holds the whole project an agent sees; the two `release-notes` cases there show the shape.

- Each skill gets at least eight trigger cases that should load it and eight near misses that should not. Each
  trigger case says whether it should load the skill and whether it is in the train or the test split, and half
  of each kind are in the test split.
- The near misses include, for each other skill in the Skills table of `AGENTS.md`, at least one request that is
  that skill's job.
- Each skill gets at least two task cases, and each task case lists what a good run must show.
- Each item a task case lists names where its rule comes from: a file and line in that case's `world/`, or
  `format` when the rule is only the shape the skill gives its own output.

## Who does what

- The goldens for a case are written by someone who did not write the case.
- The eval owner runs every round. Nobody runs a round on cases they wrote, and nobody reports a result for a
  round that has not run.
