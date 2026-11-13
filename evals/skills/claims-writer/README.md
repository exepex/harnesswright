# Evals for claims-writer

Trigger and task evals for [skills/claims-writer](../../../skills/claims-writer/SKILL.md), in the formats of
[eval-formats.md](../../../skills/skill-designer/references/eval-formats.md).

`files/` holds three small projects, each with a finished story in its run folder. They are eval fixtures written
for these tasks, not borrowed material:

- `py-discount`: Python; every acceptance criterion is met and its tests pass.
- `py-shipping`: Python; AC-3 is not implemented and its test fails, so the claims must say `not met`.
- `go-ratelimit`: Go; AC-3 needs a staging measurement, so the claims must say `not verified`.
- `py-strict`: the `py-discount` project with `scripts: forbidden` in its profile, so the skill must not run
  `claims_check.py`, must say under **Not verified** that the check did not run, and must warn the person first.

`cases/` holds the same tasks as cases of the new harness ([11 · Evals](../../../docs/design/11-evals.md)), each a
`world/` copied from its project in `files/` and a `case.json` whose expectations name checks of `evals/checks/`:
`all-criteria-met` (`py-discount`), `criterion-not-met` (`py-shipping`) and `criterion-not-verified`
(`go-ratelimit`). Each case measures every rule that `claims_check.py check` enforces, by a check or a judged
expectation, so a case never accepts claims the old check refused. A case counts a test run only when it is the
runner its project names and it ends with the exit code that world gives. `files/`, `tasks.json` and `checks/` stay
for the old runner until rounds replace it.

`story-met` is the first case for the new claims writer, in the seven-section claims format of
[contracts/claims.md](../../../contracts/claims.md): the `py-discount` project with its story in the story contract's
format (`covers`, `tests`). Its contract expectations cite the story: each criterion's outcome, and each required
test type proved by a named test. Rounds of the new skill list only the new cases; the three cases above stay for
the old skill until it is replaced.

`checks/` holds the script checks. `claims_valid.py` runs the skill's own `claims_check.py check` on the claims
file a run wrote. `code_unchanged.py` confirms that writing claims changed no project file and added none.

`tests/` holds unit tests of `claims_check.py`: `python3 -m unittest discover -s evals/skills/claims-writer/tests`.

Results per host are in `evals/results/claims-writer.json`.
