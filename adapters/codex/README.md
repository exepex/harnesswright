# OpenAI Codex adapter

Runs the Codex command line in non-interactive mode, `codex exec`, in the eval harness's jail, under the harness
contract ([adapters](../README.md#the-harness-contract)).

| Item | Value |
|---|---|
| Command | `codex exec --json --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox -c skills.bundled.enabled=false --disable view_image --disable goals -c web_search="disabled" --cd <world> [--model <model>] -` |
| Powers | The jail, not the host, confines the run: Codex's own sandbox and approvals are off |
| Prompt | Standard input (the final `-`) |
| Skill location | `<world>/.agents/skills/<name>/SKILL.md` |
| Action log | The session file every thread writes in the run's home, sub-agents included. A skill load is inferred from a command Codex parsed as a read of `skills/<name>/SKILL.md` |
| Model | `--model <model>` when the plan names one; codex-cli 0.166.0 reports no model in its events, so the plan must name it |
| Failed when | A `turn.failed` event, an `error` event in a turn that never completed, no `turn.completed` event, an exit code other than 0, or a timeout |

Codex has no separate skill tool. Its skill instructions tell the agent to open the listed `SKILL.md` before acting,
so reading that file is the skill load. An agent message that only mentions the path does not count.

## Evidence

Sources read on 2026-10-30:

- `learn.chatgpt.com/docs/non-interactive-mode`: `codex exec`, `--json` (JSON Lines on stdout), `--skip-git-repo-check`,
  and `-` to read the prompt from stdin. Event types `thread.started`, `turn.started`, `turn.completed`,
  `turn.failed`, `item.*`, `error`.
- `learn.chatgpt.com/docs/developer-commands?surface=cli`: `--model`/`-m` and `--cd`/`-C` for `codex exec`.
- `learn.chatgpt.com/docs/build-skills`: Codex reads repository skills from `.agents/skills` between the working
  directory and the repository root, and chooses a skill implicitly when the task matches its description.
- `openai/codex@615be37b2b0901b6d6810c37f02c1c7e96c99a15`, `codex-rs/ext/skills/src/catalog_prompt.rs:27-28`: for
  file skills, the agent must "open and read its `SKILL.md` completely before taking task actions".
- npm reports `@openai/codex` 0.166.0 under Apache-2.0.
- Rounds: claims-writer-codex-1 ran through this adapter. The command, plants, log, exposure and token counts are
  unit-tested in `evals/harness/tests/test_adapters.py`.
