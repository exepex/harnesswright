# Claude Code adapter

Claude Code is the reference host. This adapter runs evals through its non-interactive mode.

| Item | Value |
|---|---|
| Command | `claude -p --output-format stream-json --verbose --setting-sources project --no-session-persistence` |
| Task runs add | `--permission-mode acceptEdits`: edits inside the workspace are allowed; other actions are refused, not approved |
| Model | `--model <model>` only when the runner is given one; otherwise the host default |
| Prompt | Standard input |
| Skill location | `<workspace>/.claude/skills/<name>/SKILL.md` |
| Triggered when | An assistant `tool_use` event calls `Skill` with that skill's name, or `Read` on its `SKILL.md` |
| Failed when | A `result` event has `is_error: true`, there is no `result` event, or the exit code is not 0 |
| Environment | `CLAUDECODE` is removed, so a run can start from inside a Claude Code session |

`--setting-sources project` keeps the user's own settings out of the run. Skills the host bundles are still listed,
so a trigger eval measures the skill against them, as a real user would see it.

## Evidence

- Flags: `claude --help` of Claude Code 2.1.314 in this container lists every flag above.
- Events: a live run on 2026-10-30 of a throwaway `haiku-writer` skill emitted a `system` `init` event listing the
  skill, then an `assistant` event with `{"type": "tool_use", "name": "Skill", "input": {"skill":
  "haiku-writer", ...}}`, then a `result` event.
- Runner: `evals/runner/run_evals.py triggers` with this adapter, one run per query, scored a should-trigger query
  as triggered (1 of 1) and a should-not-trigger query as not triggered (0 of 1).
- Tests: `evals/runner/tests/test_adapters.py` pins the exact command and the trigger detection.
