# Evals for claims-writer

Trigger and task evals for [release/claims-writer](../../../release/claims-writer/SKILL.md), in the formats of
[eval-formats.md](../../../skills/skill-designer/references/eval-formats.md).

`cases/` holds the cases of the eval harness ([11 · Evals](../../../docs/design/11-evals.md)). Three task cases
measure the claims writer, in the seven-section format of [contracts/claims.md](../../../contracts/claims.md), each
a small project in its `world/` with a finished story in the story contract's format (`covers`, `tests`). The
projects are eval fixtures written for these cases, not borrowed material:

- `story-met` (`py-discount`): every criterion met.
- `story-not-met` (`py-shipping`): AC-3's test fails.
- `story-open-proof` (`go-ratelimit`): the staging latency target, NFR-1, cannot be measured here, so its
  performance test becomes an open proof item; the project README says who runs the staging load test and when.

Their contract expectations cite the story or the README and accept any wording of the outcome; the skill's own
words are format expectations. A case counts a test run only when it is the runner its project names and it ends
with the exit code that world gives. `trigger-t01` to `trigger-t20` are its trigger cases.

Results per host are in `evals/results/claims-writer.json`. Rounds run as
[ROUNDS.md](../../harness/ROUNDS.md) says.
