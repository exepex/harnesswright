# harnesswright design

These documents fix the structure of harnesswright before any skill, role or standard is written. Read them in
order; each one builds on the ones before.

| # | Document | Decides |
|---|---|---|
| 01 | [Charter](01-charter.md) | Purpose, goals, non-goals, success measures, human gates |
| 02 | [Architecture](02-architecture.md) | The six parts, the planned repository layout, formats, how a change flows |
| 03 | [Standards and rules](03-standards.md) | Layers, precedence, kinds of rule, decision points, rule format and IDs |
| 04 | [Roles](04-roles.md) | Every role, its inputs and outputs, model class, independence and access |
| 05 | [Process](05-process.md) | Change types, risk tiers, findings, voting, limits, escalation |
| 06 | [Contracts](06-contracts.md) | The files roles hand to each other |
| 07 | [Repository profile](07-repo-profile.md) | How a repository adopts the harness, capabilities and MCP |
| 08 | [Governance](08-governance.md) | Evals, versions, the learning loop, metrics, security, licences |
| 09 | [Roadmap](09-roadmap.md) | Phases, the harvest method, open questions |

## Decisions already made

| Decision | Choice |
|---|---|
| Layers apply to | Standards and process configuration. Role instructions are written once, in the core. |
| Order of work | Structure first, then a walking skeleton, then the harvest |
| Organisation and team layers | Designed now, left empty until a real need appears |
| Repository flow | Work on a branch, reviewed through a pull request |
| Licence | Apache-2.0 |

## Words used throughout

| Word | Meaning |
|---|---|
| Standard | A file of rules for one area, such as naming or tests |
| Rule | One checkable statement with an ID, a kind, a reason and a check |
| Floor | A rule no lower layer may loosen |
| Decision point | A place where teams choose differently; the core gives a default |
| Role | One job in the agent team, such as planner or judge |
| Skill | The steps a role follows for one task, in Agent Skills format |
| Contract | The fixed shape of a file one role hands to another |
| Panel | Several independent agents that vote on one judgment |
| Capability | Access to an outside system, provided by an MCP server, a CLI or nothing |
| Profile | The file a repository uses to adopt the harness |
