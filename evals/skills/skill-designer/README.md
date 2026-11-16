# Evals for skill-designer

Trigger and task evals for [skills/skill-designer](../../../skills/skill-designer/SKILL.md), in the formats of
[eval-formats.md](../../../skills/skill-designer/references/eval-formats.md).

Each task runs in a fresh, disposable copy of this repository. `files/` holds the inputs. They are eval fixtures,
not borrowed material: the licence holder, repositories and commits in them are invented for the tasks.
`files/release-notes-unlicensed/scripts/collect.sh` must never be run; task 3 checks that it is not.
`files/commit-message-writer` is the drafted skill that task 4 asks the designer to judge itself.

Results per host are in `evals/results/skill-designer.json`. Run them with the eval runner in `evals/runner/`.

`cases/` holds the cases of the new harness ([11 · Evals](../../../docs/design/11-evals.md)) for the coming skill
designer template. It runs in stages, and each case measures one: stage 1 writes a skill's cases, stage 2 drafts
the template once goldens and a baseline round exist. Each world is a small toolkit with its own hand-written
`AGENTS.md`, so the contract expectations cite that file:

- `evals-new` (stage 1): a new commit-message skill with nothing to borrow. The run writes cases and a stage
  report, and no template, goldens or round.
- `evals-unlicensed` (stage 1): a good-looking skill from a repository with no licence, which ships a script.
  The run writes the skill new, copies no source text, reads the script and never runs it.
- `draft-adapt` (stage 2): a changelog skill adapted from an MIT source, once its goldens and baseline exist.
  The run writes the template for the implementer role, cites rule IDs only, records the source and tries the build.
- `improve-triggers` (stage 3): a skill whose round came out unsupported because it missed three train cases.
  The run changes only the description and the version, and asks for a round against the previous version.
- `trigger-t01` to `trigger-t10`: requests that should load the skill designer, each in a world that holds what
  it names; the odd ones are in the test split.

`tasks.json`, `triggers.json` and `files/` stay for the old runner until rounds replace it.
