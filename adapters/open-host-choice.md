# Research note: open hosts

This is a research note. harnesswright picks no runtime or host. On 2026-11-14 the owner asked for an open host so
that graders of several model families can be compared, and a goose adapter is now planned, reaching every model
through one OpenRouter key. The note compares open hosts that read Agent Skills and can run models
from many vendors (Gemini, GPT, Grok, Kimi, DeepSeek, Qwen, Mistral, Llama and others).

## Finding: goose fit best

On these criteria, goose (`block/goose`) fit best. It is Apache-2.0, like harnesswright. It reads Agent Skills from
the same `.agents/skills/` folder as Codex. It loads a skill through one dedicated tool, which makes triggering
measurable. Its own documentation lists native providers for more of the vendors than the alternatives.

## Criteria and evidence

All sources were read on 2026-10-30. Repositories were cloned into a scratch directory outside this repository and
read, not run. No host was installed.

| Criterion | goose | opencode (runner-up) |
|---|---|---|
| Source and commit | `block/goose@090dedb7625c8aadb9bb05d68028fd00f36b429e` | `anomalyco/opencode@6700dd87b5d949a3e1748aaf998167ea881cec1b` |
| Licence | Apache-2.0 (`LICENSE` at that commit) | MIT (`LICENSE` at that commit; npm `opencode-ai@1.19.5` reports MIT) |
| Reads Agent Skills | Yes: `documentation/docs/guides/context-engineering/using-skills.md` names `.agents/skills/` and `~/.agents/skills/` as the recommended standard and says goose skills are compatible with agents that support Agent Skills | Yes: opencode.ai/docs/skills lists `.opencode/skills/`, `.claude/skills/` and `.agents/skills/`, and the Agent Skills fields `name`, `description`, `license`, `compatibility` and `metadata` |
| How a skill is loaded | Tool `load_skill` with argument `name` (`crates/goose/src/skills/client.rs:84-92`) | Tool `skill` with argument `name` (docs; emitted as `tool_use` events in `packages/cli/src/run/noninteractive.ts`) |
| Non-interactive run | `goose run -i -` (prompt on stdin), `--output-format stream-json`, `--no-session`, `--provider`, `--model` (`documentation/docs/guides/goose-cli-commands.md:427-456`) | `opencode run` (prompt on stdin), `--format json`, `--model provider/model`, `--dir` (opencode.ai/docs/cli; `packages/cli/src/run/run.ts`) |
| Native providers for the listed vendors | Anthropic, OpenAI, Gemini, xAI, Mistral AI, Meta (`documentation/docs/getting-started/providers.md`) | Anthropic, OpenAI, xAI, DeepSeek, Moonshot AI (opencode.ai/docs/providers) |
| Other vendors through gateways or local runners | DeepSeek, Kimi, Qwen and Llama through OpenRouter, Groq, Azure AI Foundry, IO Intelligence, Ollama and LM Studio | Gemini through Vertex AI; Mistral, Qwen and Llama through OpenRouter, Groq, STACKIT, Venice, Ollama and llama.cpp; no direct Google Gemini, Mistral or Alibaba provider is listed |

## Other hosts considered

| Host | Reason |
|---|---|
| opencode | Meets every criterion and is the runner-up. Its documentation lists fewer of the listed vendors as direct providers. |
| Gemini CLI (`@google/gemini-cli`, Apache-2.0) | Runs Google's models only, so it fails the many-vendors criterion. It can be added later as its own host. |
| Crush (`@charmland/crush`) | npm reports the licence `FSL-1.1-MIT`, which is not an open source licence until its change date. |

## What is not verified

- No live run: goose is not installed here, and no model credentials for it exist in this container.
- The exact `stream-json` event that carries a `load_skill` call has not been read yet. It must be confirmed from
  the source, and by a live run, if an adapter is ever built.
- Paid services: goose and its local runners are free. A hosted model needs the owner's own account and key.
