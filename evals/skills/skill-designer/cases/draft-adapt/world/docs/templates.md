# Templates

How a skill's template is written. This is stage 2 of a skill: stage 1 wrote its cases, and stage 3 lists it in
`AGENTS.md` once a round with the skill has verified it.

## What stage 2 may change

Writing a new skill's template changes only `v2/skills/<name>/`, `v2/roles.md`, `THIRD_PARTY.md`, `v2/VERSION`
and the stage report, `evals/skills/<name>/stage-2.md`. Notes for yourself go under `.harness/runs/`. Every other
file stays as it is, `AGENTS.md`, the cases and the labels included.

Stage 2 ends with that report, which lists every file the stage wrote, like the stage 1 report beside it.

## Version

`v2/VERSION` holds the toolkit's version as three numbers. A new skill raises the middle number and sets the last
one to 0. A change to a skill that is already there raises the last number.

## Rules in a template

A template cites each rule it applies by its ID in `v2/rules/index.md`, next to the step that applies it. It never
says what a rule says, in the index's words or in its own. Where a borrowed skill has a sentence that says what a
listed rule says, the template keeps the step's action, drops that sentence and cites the rule's ID instead.
