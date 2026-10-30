# 10 · Skills: sourcing, design and portability

Every skill in harnesswright is designed by the skill designer, sourced borrow-first, written to run the same way
on every supported agent host, and proven by evals before release.

## Borrow first

Before a skill is written, the skill designer searches what already exists: skills published by Anthropic,
OpenAI, Google, Microsoft and GitHub, security firms such as Trail of Bits, and community libraries. Each skill
then takes one of three paths:

| Path | When | What we do |
|---|---|---|
| **Adopt** | An existing skill already meets the quality checklist below | Copy it unchanged, record its source |
| **Adapt** | A good skill has gaps, host-specific parts or a different voice | Copy it, improve it, record the source and what changed |
| **Write new** | Nothing good exists | Write our own |

Licences decide what may be copied (see [08 · Governance](08-governance.md)). A skill without a licence can
inspire ours but is never copied.

Every borrowed or adapted skill carries its provenance in `metadata` frontmatter, which the Agent Skills format
allows:

```yaml
metadata:
  source: anthropics/skills@<commit> skills/skill-creator
  source-licence: Apache-2.0
  sourcing: adapted       # adopted | adapted | new
```

`THIRD_PARTY.md` lists every source, and adapted skills keep the original licence notice where it requires that.

## The quality checklist

A skill is production grade only when it has all of these:

1. **Purpose and limits:** what the skill does, and what it does not do.
2. **Triggers:** a `description` that says what the skill does and when to use it, with concrete phrases and file
   types, plus cases where it must not trigger.
3. **Inputs:** what the skill needs, and what to do when an input is missing.
4. **Steps:** numbered and specific, each one checkable.
5. **Standards by ID:** the rules it applies are cited by rule ID, not repeated.
6. **Verification:** how the agent proves it did the job: a command, a test, a check.
7. **Failure handling:** what to do when a step fails, and when to stop and ask one clear question.
8. **Output:** written in the matching contract from [06 · Contracts](06-contracts.md).
9. **Examples:** at least one good and one bad example.
10. **Evals:** trigger evals (should and should not trigger) and task evals (the result is right).
11. **Portability:** passes the portability rules and the portability evals below.
12. **Size:** `SKILL.md` under 500 lines; detail moves to `references/`.

## Portability

The same skills must run on Claude Code, OpenAI Codex and hosts that run other models, such as Kimi and DeepSeek
models, with the same behaviour.

### What can and cannot be promised

The **text, scripts and contracts** of a skill can be identical everywhere, and they will be. The **behaviour**
cannot be guaranteed identical. Different models follow the same instructions with different skill, and different
hosts load and trigger skills in different ways. So harnesswright does three things instead of promising zero
variance:

1. It writes skills so that as little as possible depends on the model or host (the rules below).
2. It measures the behaviour on every supported host with the same evals.
3. It releases a skill as portable only when every supported host passes within a set tolerance of the reference
   host. A host that falls short is listed as unsupported for that skill until it passes.

### Portability rules

These are rules of harnesswright itself, for writing harness skills, like the `HW-AG` rules in `AGENTS.md`. They
are not layered standards: they do not use the rule format of [03 · Standards](03-standards.md), no layer of a
consuming repository can override or loosen them, and they change only through a change to this document.

| ID | Rule |
|---|---|
| `HW-PORT-01` | Frontmatter uses only fields from the Agent Skills specification: `name` (matching the folder name), `description`, and optionally `license`, `compatibility` and `metadata` (string values only). The experimental `allowed-tools` field is not used, because hosts treat it differently. Host-specific fields live in adapters. |
| `HW-PORT-02` | The body names no host tool (such as a host's sub-agent, skill or patch tool). It uses plain verbs: "run the command", "read the file", "start an independent reviewer". |
| `HW-PORT-03` | A step that needs a host feature names the capability. Where the step needs no independence, such as parallel work, the skill gives a fallback that works in a single agent, in sequence. Where it needs independence (a reviewer, judge, verifier or panel voter), there is no in-session fallback: the step runs in a fresh, separate agent that receives only the contracts and the change, as [04 · Roles](04-roles.md) requires. If the host cannot start one, the coordinator stops and escalates to the human. |
| `HW-PORT-04` | Logic that must give the same result everywhere goes in a script, not in prose. Scripts use Python 3 with only the standard library, or POSIX `sh`, make no network calls and are deterministic. |
| `HW-PORT-05` | The repository's `AGENTS.md` lists every skill with its path and trigger, so a host that does not load skills automatically can still find and read them. |
| `HW-PORT-06` | Outputs follow the contracts, so results from different hosts can be compared field by field. |
| `HW-PORT-07` | Instructions are explicit. Nothing relies on a habit of one model, such as guessing an unstated output format. |

### Host adapters

Anything host-specific lives in `adapters/<host>/`, never in a skill: how skills are installed, how roles become
that host's agent definitions, how sub-agents are started, which model each model class maps to, and how evals run.
The first adapters planned are Claude Code (the reference host), OpenAI Codex, and one open host able to run Kimi
and DeepSeek models, chosen in phase 2.

### Portability evals

Each skill's evals run on every supported host with the same inputs. The default thresholds, which the owner can
change, are:

| Measure | Default |
|---|---|
| Task eval pass rate on each host | At least 90% |
| Gap to the reference host | At most 10 percentage points |
| Trigger accuracy on each host | At least 90% of should-trigger and should-not-trigger cases |

## The skill designer

The skill designer is the role that makes and improves every skill. Its skill starts from Anthropic's
skill-creator (Apache-2.0), which drafts skills, runs evals, benchmarks variants and tunes descriptions for
triggering. We adapt it in three ways:

1. **Our checklist and formats:** the quality checklist above, the rule IDs, the contracts and the borrow-first
   search.
2. **Portability:** skill-creator's eval scripts run the Claude Code CLI directly. The adapted runner calls a host
   adapter instead, so the same evals run on every supported host.
3. **Independent review:** a skill the designer produces is judged by a separate agent before release, like any
   other change.

The designer's process for one skill:

1. Write the purpose, limits and triggers.
2. Search existing skills and choose adopt, adapt or write new.
3. Draft the skill against the checklist.
4. Write trigger and task evals.
5. Run them on the reference host and improve the skill until they pass.
6. Run them on every supported host and fix what fails, keeping the skill host-neutral.
7. Record provenance and hand the skill, its evals and the results to a judge.
