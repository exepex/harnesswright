# OpenAI Codex adapter

Runs evals through the Codex command line in non-interactive mode, `codex exec`.

| Item | Value |
|---|---|
| Command | `codex exec --json --ephemeral --skip-git-repo-check --sandbox <mode> --cd <workspace> -` |
| Sandbox | `read-only` for trigger runs; `workspace-write` for task runs. Never `danger-full-access`. |
| Model | `--model <model>` only when the runner is given one; otherwise the host default |
| Prompt | Standard input (the final `-`) |
| Skill location | `<workspace>/.agents/skills/<name>/SKILL.md` |
| Triggered when | A `command_execution` item whose command runs a file-printing command (`cat`, `sed`, `head` and similar) on `skills/<name>/SKILL.md`, or an `mcp_tool_call` whose arguments name that file. Command output is never inspected. |
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

## Not run

There is no `codex` command and no OpenAI credential in this container. The adapter is unit-tested against the
documented command and event format only. Its trigger detection still needs a live run, which needs the owner to
provide the command and a credential.
