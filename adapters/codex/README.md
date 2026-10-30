# OpenAI Codex adapter

Runs evals through the Codex command line in non-interactive mode, `codex exec`.

| Item | Value |
|---|---|
| Command | `codex exec --json --ephemeral --skip-git-repo-check --sandbox <mode> --cd <workspace> -` |
| Sandbox | `read-only` for trigger runs; `workspace-write` for task runs, plus `--add-dir <scratch>` for tool caches. Never `danger-full-access`. |
| Refused when | Never: `codex exec` asks no one for approval. A command the sandbox blocks fails, and the model sees the error, as on Claude Code |
| Model recorded | A `model` field in any event; codex-cli 0.166.0 emits none, so pass `--model` or the label stays `incomplete` |
| Model | `--model <model>` only when the runner is given one; otherwise the host default |
| Prompt | Standard input (the final `-`) |
| Skill location | `<workspace>/.agents/skills/<name>/SKILL.md` |
| Triggered when | A `command_execution` item with a simple command that names `skills/<name>/SKILL.md` and can read it: anything except path-only commands such as `ls`, `find`, `stat`, `test` and `echo`. So `cat`, `sed`, `rg`, `grep`, `wc` and `python3 -c "open(...)"` all count. `bash -lc '...'` wrappers are unwrapped and `&&`, `;` and `|` split the commands. An `mcp_tool_call` whose arguments name that file also counts. Command output is never inspected. |
| Failed when | A `turn.failed` or `error` event arrives, there is no `turn.completed` event, the exit code is not 0, or a task run times out |

Codex has no separate skill tool. Its skill instructions tell the agent to open the listed `SKILL.md` before acting,
so reading that file is the trigger signal. An agent message that only mentions the path does not count.

## Evidence

Sources read on 2026-10-30:

- `learn.chatgpt.com/docs/non-interactive-mode`: `codex exec`, `--json` (JSON Lines on stdout), `--ephemeral`,
  `--sandbox` with `read-only` (default) and `workspace-write`, `--skip-git-repo-check`, and `-` to read the prompt
  from stdin. Event types `thread.started`, `turn.started`, `turn.completed`, `turn.failed`, `item.*`, `error`; item
  types include agent messages, command executions and MCP tool calls.
- `learn.chatgpt.com/docs/developer-commands?surface=cli`: `--model`/`-m` and `--cd`/`-C` for `codex exec`.
- `learn.chatgpt.com/docs/build-skills`: Codex reads repository skills from `.agents/skills` between the working
  directory and the repository root, and chooses a skill implicitly when the task matches its description.
- `openai/codex@615be37b2b0901b6d6810c37f02c1c7e96c99a15`, `codex-rs/ext/skills/src/catalog_prompt.rs:27-28`: for
  file skills, the agent must "open and read its `SKILL.md` completely before taking task actions".
- npm reports `@openai/codex` 0.166.0 under Apache-2.0.

## Not run here

The phase-2 sample-skill work ran this adapter live. This change was tested without an OpenAI credential:
`codex exec --help` of codex-cli 0.166.0 lists `--add-dir` ("Additional directories that should be writable
alongside the primary workspace"), and the item statuses in that binary are `in_progress`, `completed` and
`failed`, with no declined status. The command and trigger detection are unit-tested.
