# Claude Code adapter

Claude Code is the reference host. This adapter runs evals through its non-interactive mode.

| Item | Value |
|---|---|
| Command | `claude -p --output-format stream-json --verbose --setting-sources project --no-session-persistence` |
| Task runs add | `--permission-mode acceptEdits --settings '{"sandbox": {"enabled": true, "autoAllowBashIfSandboxed": true, "allowUnsandboxedCommands": false}}' --add-dir <scratch>` |
| Task powers | Commands run without a prompt inside the host's sandbox: writes only in the workspace and the scratch folder, network blocked. A command the sandbox cannot hold is refused, never run outside it. The same powers as Codex's `workspace-write`. |
| Needs | On Linux, `bwrap` and `socat` on PATH for the sandbox (`apt install bubblewrap socat`). Without them the host refuses every command, so the runner marks task runs `not run` |
| Refused when | The `result` event lists `permission_denials`; the runner then fails the task run |
| Model recorded | The `model` field of the `system` `init` event |
| Model | `--model <model>` only when the runner is given one; otherwise the host default, read back from the init event |
| Prompt | Standard input |
| Skill location | `<workspace>/.claude/skills/<name>/SKILL.md` |
| Triggered when | An assistant `tool_use` event calls `Skill` with that skill's name, or `Read` on its `SKILL.md` |
| Failed when | A `result` event has `is_error: true`, there is no `result` event, the exit code is not 0, or a task run times out |
| Environment | `CLAUDECODE` is removed, so a run can start from inside a Claude Code session |

`--setting-sources project` keeps the user's own settings out of the run. Skills the host bundles are still listed,
so a trigger eval measures the skill against them, as a real user would see it.

## Evidence

- Task powers, live on 2026-10-30 with Claude Code 2.1.314: with `acceptEdits` alone, `python3 t.py` came back
  "This command requires approval" in `permission_denials` and the run still exited 0. With the sandbox settings
  above, `python3 t.py` and `go test ./...` ran, `touch /tmp/outside` failed with "Read-only file system", and
  `curl https://example.com` was blocked by the sandbox. Without `bwrap` and `socat` the host printed "Sandbox
  disabled" and refused the commands again. Go's build cache needs the scratch folder (`XDG_CACHE_HOME`, added
  with `--add-dir`); without it `go test` fails on the read-only home folder.
- Runner, live: a throwaway skill whose task runs `go test` passed its script check through `run_evals.py tasks`,
  with no refusals and the model `claude-sonnet-5-5` recorded from the init event.

- Flags: `claude --help` of Claude Code 2.1.314 in this container lists every flag above.
- Events: a live run on 2026-10-30 of a throwaway `haiku-writer` skill emitted a `system` `init` event listing the
  skill, then an `assistant` event with `{"type": "tool_use", "name": "Skill", "input": {"skill":
  "haiku-writer", ...}}`, then a `result` event.
- Runner: `evals/runner/run_evals.py triggers` with this adapter, one run per query, scored a should-trigger query
  as triggered (1 of 1) and a should-not-trigger query as not triggered (0 of 1).
- Tests: `evals/runner/tests/test_adapters.py` pins the exact command and the trigger detection.
