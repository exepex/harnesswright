# Templates

How a skill's template is written. This is stage 2 of a skill: stage 1 wrote its cases, and stage 3 lists it in
`AGENTS.md` once a round with the skill has verified it.

## What stage 2 may change

Writing a new skill's template changes only `v2/skills/<name>/`, `v2/roles.md`, `THIRD_PARTY.md`, `v2/VERSION`,
`release/`, which the build writes, and the stage report, `evals/skills/<name>/stage-2.md`. Notes for yourself
go under `.harness/runs/`. Every other file stays as it is, `AGENTS.md`, the cases and the labels included.

Stage 2 ends with that report, which lists every file the stage wrote by its own path, one per line. A folder, a
pattern or a count does not list the files in it.

## Version

`v2/VERSION` holds the toolkit's version as three numbers. A new skill raises the middle number and sets the last
one to 0. A change to a skill that is already there raises the last number.

## Rules in a template

A template cites each rule it applies only by a rule tag, `{{rule:<ID>}}`, where `<ID>` is an ID from
`v2/rules/core/index.md`. The tag goes on a `Rules:` line just below the step that applies the rule. A `Rules:`
line is one line, indented like its step, that holds `Rules: ` and then the tags, separated by ", ", and nothing
else. No other line holds a tag or a rule ID, and the frontmatter holds neither. The build writes each tag out as
the rule's ID and title.

Where a borrowed skill has a sentence that says what a listed rule says, the template drops that sentence and tags
the rule instead. It keeps the step's own action and any check on the step's own output.

## Build

After you change a template, run `python3 v2/build/build.py` and report what it printed.
