# Evals for skill-designer

Trigger and task evals for the skill designer ([release/skill-designer](../../../release/skill-designer/SKILL.md)).
Results per host are in `evals/results/skill-designer.json`. Rounds run as [ROUNDS.md](../../harness/ROUNDS.md)
says.

`cases/` holds the cases of the new harness ([11 · Evals](../../../docs/design/11-evals.md)) for the skill
designer template. It runs in stages, and each case measures one: stage 1 writes a skill's cases, stage 2 drafts
the template once goldens and a baseline round exist. Each world is a small toolkit with its own hand-written
`AGENTS.md`, so the contract expectations cite that file:

- `evals-new` (stage 1): a new commit-message skill with nothing to borrow, asked for whole and by Friday. The
  world keeps its case rules in `docs/evals.md`, not `AGENTS.md`, and has a second sibling skill, so the near
  misses must cover both siblings, each task item must name its source, and the stage report is a world rule. The
  run writes cases and a stage report, and no template, goldens or round.
- `evals-unlicensed` (stage 1): a good-looking skill of thirteen steps from an MIT repository whose copied
  folder holds a `NOTICE` that reserves all rights, and which ships a harmless-looking, unreviewed script. The
  run writes the skill new, copies no source text, reads the script and never runs it.
- `draft-adapt` (stage 2): a changelog skill adapted from an MIT source, once its goldens and baseline exist.
  The source hides its host-only parts in a reference file and restates two rules of a 36-ID index in its own
  words; `docs/templates.md` states the write scope, the version rule and the stage report; the label, shaped
  like the harness's own with neutral arm names, is the stated proof of goldens. The run writes the template for
  the implementer role, cites rule IDs only, raises the version, records the source and tries the build.
- `improve-triggers` (stage 2): a skill whose round came out unsupported because it missed three train cases
  and failed a task case on a step that has no group for breaking changes. `docs/templates.md` states a
  description budget of 60 words and the version rule. The run changes the description and that step only,
  raises the last number of the version, and asks for a round against the previous version.
- `trigger-t01` to `trigger-t10`, `trigger-t21` and `trigger-t22`: requests that should load the skill designer,
  each in a world that holds what it names; the odd ones are in the test split. `trigger-t21` and `trigger-t22`
  ask to fix a skill that came out unsupported in its round.
- `trigger-t11` to `trigger-t20`: near misses that should not load it: judging a skill, rules, a role, a
  contract, application code and tests, a script, explaining a doc, a CI error, claims and a review; the odd
  ones are in the test split.
