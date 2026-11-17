# Templates

How a skill's template is written. This is stage 2 of a skill: stage 1 wrote its cases, and stage 3 lists it in
`AGENTS.md` once a round with the skill has verified it.

## What stage 2 may change

Writing a new skill's template changes only `v2/skills/<name>/`, `v2/roles.md`, `THIRD_PARTY.md`, `v2/VERSION`
and the stage report, `evals/skills/<name>/stage-2.md`. Notes for yourself go under `.harness/runs/`. Every other
file stays as it is, `AGENTS.md`, the cases and the labels included.

Stage 2 ends with that report, which lists every file the stage wrote by its own path, one per line. A folder, a
pattern or a count does not list the files in it.

## Version

`v2/VERSION` holds the toolkit's version as three numbers. A new skill raises the middle number and sets the last
one to 0. A change to a skill that is already there raises the last number.

## Rules in a template

A template cites each rule it applies by its ID in `v2/rules/index.md`, next to the step that applies it. Beside
the ID it may repeat the index's short reminder for that ID, and nothing more of the rule. Where a borrowed skill
has a sentence that says what a listed rule says, the template drops that sentence and cites the rule's ID
instead. It keeps the step's own action and any check on the step's own output, such as reading the file back to
see the new line: those say what to do here, not what the rule says in general.
Where the only thing a step would keep is the duty a listed rule already states, the template writes it as a check
of what that step produced, with the ID beside it. A step that adds a heading, for example, keeps "Check: the
heading, read back, names no customer (CORE-WORK-06)" and drops "Never put a customer's name in a file
(CORE-WORK-06)": the first checks what this step made, the second restates the rule.
