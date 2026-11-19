# Claude Code adapter

Claude Code is the reference host. This adapter runs it in the eval harness's jail through its non-interactive
mode, under the harness contract ([adapters](../README.md#the-harness-contract)).

| Item | Value |
|---|---|
| Command | `claude -p --output-format stream-json --verbose --setting-sources project --no-session-persistence --dangerously-skip-permissions --settings <JAIL_SETTINGS> --tools <TOOLS> [--model <model>]` |
| Powers | The jail, not the host, confines the run: the host's permission checks are off and it gets only the tools in `TOOLS` |
| Bundled skills | Off: `disableBundledSkills`, the two skills that survive it turned off by `skillOverrides`, and the built-in plugins off |
| Prompt | Standard input |
| Skill location | `<world>/.claude/skills/<name>/SKILL.md` |
| Action log | Each assistant `tool_use` event paired with its result: commands, reads, writes, skill loads and agents |
| Exposure | The skills and tools of the `system` `init` event |
| Tokens | The last `result` event's `modelUsage` by model, else its `usage` under the init event's model |
| Failed when | A `result` event has `is_error: true`, there is no `result` event, the exit code is not 0, or the run timed out |
| Environment | `CLAUDECODE` is removed, so a run can start from inside a Claude Code session; `IS_SANDBOX=1` lets it skip permissions as root, as the jail is its sandbox |

`--setting-sources project` keeps the user's own settings out of the run.

## Evidence

- Flags: `claude --help` of Claude Code 2.1.314 lists every flag above.
- Events: a live run on 2026-10-30 of a throwaway `haiku-writer` skill emitted a `system` `init` event listing the
  skill, then an `assistant` event with `{"type": "tool_use", "name": "Skill", "input": {"skill":
  "haiku-writer", ...}}`, then a `result` event.
- Rounds: the probes, harness faults and rounds of both skills ran live through this adapter (claims-writer-6,
  skill-designer-8 and -9).
- Tests: `evals/harness/tests/test_adapters.py` pins the exact command, the plants, the log, the exposure and the
  token counts.
