# Third-party sources

Every source that harnesswright copied or adapted text or code from. Licences decide what may be copied; see
[08 · Governance](docs/design/08-governance.md). Each entry records the source repository, commit, path and
licence, and whether the material was adopted, adapted or written new.

## anthropics/skills · skill-creator

| Field | Value |
|---|---|
| Repository | https://github.com/anthropics/skills |
| Commit | `ca45fc496a3436251f191354091d557da31c15b5` |
| Path | `skills/skill-creator` |
| Licence | Apache-2.0, Copyright 2026 Anthropic, PBC. Full text kept in `skills/skill-designer/LICENSE.txt`, `v2/skills/skill-designer/LICENSE.txt` and `release/skill-designer/LICENSE.txt`. |
| Sourcing | adapted |
| Used in | `skills/skill-designer/`, `v2/skills/skill-designer/` and the release skill built from it, `release/skill-designer/` |

### What was taken and what changed

| harnesswright file | Source file | Changes |
|---|---|---|
| `skills/skill-designer/SKILL.md` | `SKILL.md` | Rewritten around the seven-step designer process of [10 · Skills](docs/design/10-skills.md). Added borrow-first search, the quality checklist, rule IDs, contracts, the `HW-PORT` rules, per-host eval runs and the hand-off to an independent judge. Removed host-specific parts: named tools, the browser viewer, packaging and product-specific sections. Kept the ideas on writing descriptions, realistic trigger queries, near-miss negatives, discriminating expectations, baselines, generalising from feedback and held-out description tuning. |
| `skills/skill-designer/references/eval-formats.md` | `references/schemas.md` | Kept the evals and grading formats in a reduced form; added trigger IDs, script checks and the `evals/skills/<name>/` layout; removed history, timing, metrics, benchmark and viewer formats. |
| `skills/skill-designer/references/grader.md` | `agents/grader.md` | Shortened; runs as an independent agent; reads script check results; no host tool names; output limited to the reduced grading format. |
| `skills/skill-designer/references/comparator.md` | `agents/comparator.md`, `agents/analyzer.md` | Merged and shortened into one blind comparison and one analysis; simplified output; benchmark analysis removed. |
| `skills/skill-designer/LICENSE.txt` | `LICENSE.txt` | Unchanged, except a final newline added. |
| `v2/skills/skill-designer/SKILL.tmpl.md`, built into `release/skill-designer/SKILL.md` | `SKILL.md` | Rewritten as a template from the adapted skill above. The work runs in three stages (evals, draft, ship), one per run, each ending with a stage report that names the next step's owner. Evals come before the skill; goldens, rounds and judging are left to other agents. Rules are cited by ID. Kept the ideas on descriptions that say when to use a skill and when not, realistic trigger prompts, near-miss negatives, a held-out test split and baselines without the skill. |
| `v2/skills/skill-designer/LICENSE.txt`, copied to `release/skill-designer/LICENSE.txt` | `LICENSE.txt` | Copied from `skills/skill-designer/LICENSE.txt`. |
| `evals/harness/rounds.py`, `evals/harness/labels.py`, `evals/harness/cases.py` | `scripts/run_eval.py`, `scripts/run_loop.py` | Written new; no code copied. Ideas taken (first in the phase 2 runner, now in the harness): several runs per trigger query, a trigger-rate threshold of 0.5, a held-out test split of trigger cases, and from `scripts/aggregate_benchmark.py` and `references/schemas.md`: 3 runs per configuration and the with-skill minus without-skill delta (`lift`). The host is reached through an adapter instead of `claude -p`. |

Not taken: `scripts/`, `eval-viewer/`, `assets/eval_review.html` and `agents/` files other than those above. The
eval scripts call the Claude Code command line directly (`claude -p` in `scripts/run_eval.py` and
`scripts/improve_description.py`); harnesswright replaces them with a host-neutral eval harness and host adapters.

## obra/superpowers · verification-before-completion

| Field | Value |
|---|---|
| Repository | https://github.com/obra/superpowers |
| Commit | `2ce8aa15d05bd57213e6f746f953aafb7ded7a8b` |
| Path | `skills/verification-before-completion` |
| Licence | MIT, Copyright (c) 2025 Jesse Vincent. Full text kept in `v2/skills/claims-writer/LICENSE-MIT.txt` and `release/claims-writer/LICENSE-MIT.txt`. |
| Sourcing | adapted |
| Used in | `v2/skills/claims-writer/` and the release skill built from it, `release/claims-writer/` |

### What was taken and what changed

| harnesswright file | Source file | Changes |
|---|---|---|
| `v2/skills/claims-writer/SKILL.tmpl.md`, built into `release/claims-writer/SKILL.md` | `SKILL.md` | Kept the core idea (no completion claim without fresh evidence), the gate of identify, run, read and verify before claiming, and the table of what proves a claim and what is not enough, reworded. The table drops the source's lint, regression red-green and agent-completed rows, and adds rows for a behaviour that exists and for a covered test type. Written as a template that cites rule IDs (CORE-WORK-01 to 03) instead of stating them. The output is the claims contract of `contracts/claims.md`: a status per requirement, test types, open proof items and the Standards section with its sources. Added purpose and limits, inputs, numbered steps with checks, failure handling, examples, bundled check scripts and a fallback for when scripts are forbidden or cannot run (`HW-PORT-08`). Removed the rationalisation and red-flag lists and the emphatic wording, in favour of reasons. |
| `v2/skills/claims-writer/LICENSE-MIT.txt`, copied to `release/claims-writer/LICENSE-MIT.txt` | `LICENSE` | Unchanged. |

Not taken: the rest of the repository. Its other skills were read only to choose a candidate.

## Rulebook v2 · ideas only

The rules in `v2/rules/` are written new. No text was copied. Each rule's Source names where its idea came from.

| Repository | Commit | Paths read | Licence | Sourcing |
|---|---|---|---|---|
| https://github.com/anthropics/skills | `ca45fc496a3436251f191354091d557da31c15b5` | `skills/skill-creator/` | Apache-2.0 | written new |
| https://github.com/obra/superpowers | `2ce8aa15d05bd57213e6f746f953aafb7ded7a8b` | `skills/writing-skills/`, `skills/verification-before-completion/` | MIT | written new |
| https://github.com/exepex/stratum | `cc3ea82271d9624267079d3b5fe456c74073102f` | `AGENTS.md`, `docs/agents/` | Apache-2.0 | written new |
| https://github.com/anthropics/claude-plugins-official | `a2e251d9b97b909bf728b3e84fc8d17e6aba0063` | `plugins/plugin-dev/skills/plugin-structure/`, `plugins/hookify/hooks/`, `plugins/feature-dev/commands/` | Apache-2.0 | written new |
| https://github.com/anthropics/claude-code | `964d69565952a176ac1975ed218362991db71433` | `CHANGELOG.md` | all rights reserved | idea only, written new |

## block/goose · two build switches

| Field | Value |
|---|---|
| Repository | https://github.com/block/goose |
| Commit | `e62a656f460d6399b34c747014d810727ff70b05` (tag v1.59.1) |
| Path | `crates/goose/src/skills/mod.rs`, `crates/goose/src/providers/utils.rs` |
| Licence | Apache-2.0. The patch holds a few of goose's own lines as context. |
| Sourcing | written new |
| Used in | `adapters/goose/goose.patch` |

The patch adds two switches: `GOOSE_BUILTIN_SKILLS` keeps goose's bundled skills out of a run, and
`GOOSE_REQUEST_LOGS_KEEP_ALL` keeps every request log under the name goose gives it at the start, never renamed. It is applied to a goose checkout to build the
program the goose adapter runs; harnesswright ships no goose code.
