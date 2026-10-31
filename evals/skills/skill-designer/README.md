# Evals for skill-designer

Trigger and task evals for [skills/skill-designer](../../../skills/skill-designer/SKILL.md), in the formats of
[eval-formats.md](../../../skills/skill-designer/references/eval-formats.md).

Each task runs in a fresh, disposable copy of this repository. `files/` holds the inputs. They are eval fixtures,
not borrowed material: the licence holder, repositories and commits in them are invented for the tasks.
`files/release-notes-unlicensed/scripts/collect.sh` must never be run; task 3 checks that it is not.

Results per host are in `evals/results/skill-designer.json`. Run them with the eval runner in `evals/runner/`.
