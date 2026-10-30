# 02 · Architecture

## Six parts, kept separate

| Part | Answers | Varies by | Lives in |
|---|---|---|---|
| **Standards** | What does good work look like? | Layer: core, language, organisation, team, repository | `standards/`, and `.harness/standards/` in each repository |
| **Roles** | Who does each job, and how? | Nothing. Roles are written once, in the core. | `roles/` |
| **Skills** | What steps does a role follow for one task? | Nothing. Skills read the resolved standards. | `skills/` |
| **Process** | Which roles run, in what order, with how many voters? | Change type, risk tier and configuration | `process/`, overridden by the repository profile |
| **Contracts** | What do roles hand to each other? | Nothing. Formats are fixed. | `contracts/` |
| **Capabilities** | How does a role reach outside systems? | Repository: MCP server, CLI or nothing | Repository profile |

A seventh part, **governance** (evals, versioning, metrics, the learning loop), keeps the other six honest. See
[08 · Governance](08-governance.md).

In one sentence: **roles use skills to apply standards, process decides which roles run, contracts are what they
pass between them, and capabilities are how they reach the outside world.**

### Why roles are not layered

Teams differ in *what* they enforce, not in *how* a judge or a planner does its job. If every layer could rewrite
every role, there would be dozens of role variants drifting apart, and no two repositories would be judged the same
way. So a team changes the rules (standards) and the knobs (process configuration: panel sizes, gates, models,
budgets), never the role instructions.

## Planned repository layout

```text
harnesswright/
├── README.md
├── LICENSE                     Apache-2.0
├── THIRD_PARTY.md              Where borrowed ideas and text came from, with licences
├── docs/design/                These design documents
├── standards/
│   ├── core/                   Principles and floors for every language, one file per area
│   ├── languages/<language>/   Idioms, decision-point defaults and the toolchain for one language
│   ├── org/                    Empty until needed
│   └── team/                   Empty until needed
├── roles/                      One agent definition per role
├── skills/                     Agent Skills (SKILL.md folders) for each repeatable task
├── process/                    Default change types, risk tiers, pipelines and panel settings
├── contracts/                  Templates: plan, story, claims, finding, vote, verdict
├── evals/                      The harness's own test tasks, expected outcomes and sample projects
└── adapters/<host>/            Everything host-specific: installation, agent definitions, sub-agents, models, eval runs
```

The repository layer and the profile live in each consuming repository, under `.harness/`. See
[07 · Repository profile](07-repo-profile.md).

## Formats

- **Skills** follow the open Agent Skills format: a folder holding a `SKILL.md` with `name` and `description`
  frontmatter, plus optional `references/`, `scripts/` and `assets/`. Agents load a skill only when a task needs it,
  so many skills cost little context. The same skill files run on every supported host; see the portability rules
  in [10 · Skills](10-skills.md).
- **Roles** are plain Markdown instructions with no host-specific fields. Each host adapter turns them into that
  host's agent definitions, such as Claude Code agent files, and maps each model class to a model.
- **Standards and contracts** are Markdown with a small amount of YAML frontmatter, so both people and agents can
  read them.
- **Process and the profile** are YAML.

## How one change flows

```text
request ──► triage ──► picks change type + risk tier ──► pipeline from process/
                                    │
     ┌──────────────────────────────┴──────────────────────────────┐
     ▼                                                             ▼
 (tier 3) architect + planner panel ─► plan vote ─► human gate   (tiers 0–2) skip planning
     ▼
 story writer ─► alignment judges: do the stories cover the plan?
     ▼
 per story: implementer ─► toolchain checks ─► reviewers (code, tests, security)
            ─► story judges ─► rework or pass
     ▼
 feature judges ─► scenario testers ─► release review ─► human merge gate
```

Each arrow hands over a contract file. Every step records its result in the run folder, so a run can be resumed
and audited. See [05 · Process](05-process.md) and [06 · Contracts](06-contracts.md).

## What each part does not do

- Standards never say who runs or when.
- Roles never contain rules about code. They point to standards by rule ID.
- Process never contains rules about code or role instructions. It holds numbers and names only.
- Contracts never contain instructions. They are shapes to fill in.
