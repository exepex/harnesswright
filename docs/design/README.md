# harnesswright design

These documents fix the structure of harnesswright before any skill, role or standard is written. Read them in
order; each one builds on the ones before.

| # | Document | Decides |
|---|---|---|
| 01 | [Charter](01-charter.md) | Purpose, goals, non-goals, success measures, human gates |
| 02 | [Architecture](02-architecture.md) | The six parts, the planned repository layout, formats, how a change flows |
| 03 | [Standards and rules](03-standards.md) | Layers, precedence, kinds of rule, decision points, rule format and IDs |
| 04 | [Roles](04-roles.md) | Jobs, model classes, independence and access; the roles themselves are listed in [v2/roles.md](../../v2/roles.md) |
| 05 | [Process](05-process.md) | Change types, risk tiers, findings, voting, limits, escalation |
| 06 | [Contracts](06-contracts.md) | The files roles hand to each other |
| 07 | [Repository profile](07-repo-profile.md) | How a repository adopts the harness, capabilities and MCP |
| 08 | [Governance](08-governance.md) | Evals, versions, the learning loop, metrics, security, licences |
| 09 | [Roadmap](09-roadmap.md) | Phases, the harvest method, open questions |
| 10 | [Skills](10-skills.md) | Borrow-first sourcing, the quality checklist, portability across hosts, the skill designer |
| 11 | [Evals](11-evals.md) | How skills are measured: worlds, containment, equal powers, evidence, scoring, judge-owned faults, rounds |

## Decisions already made

| Decision | Choice |
|---|---|
| Layers apply to | Standards and process configuration. Role instructions are written once, in the core. |
| Order of work | Structure first, then a walking skeleton, then the harvest |
| Company, department and team layers | Optional; designed now |
| Repository flow | Work on a branch, reviewed through a pull request |
| Licence | Apache-2.0 |
| Where work happens | Everything is built and tested inside harnesswright, on sample projects under `evals/fixtures/` |
| Hosts | The same skills run on Claude Code, OpenAI Codex and hosts for other models; behaviour is measured per host |
| Sourcing | Borrow first: adopt, adapt or write new, with source and licence recorded |
| Skill design | Every skill is made by the skill designer, adapted from Anthropic's skill-creator |

## Words used throughout

Every document uses these words with these meanings. Do not use other words for them.

| Word | Meaning |
|---|---|
| Skill | The steps for one job, such as "review code", in Agent Skills format. harnesswright writes every skill. |
| Role | One job in the agent team, such as story judge. Each role uses one or more skills. |
| Rule | What good work looks like, such as "money is always in cents". Each rule has a unique ID, a title and a body, and lives in one place only. |
| Floor | A minimum that is never traded away, such as "no secret in code". A more specific layer may only make it stricter. |
| Decision point | A place where good teams choose differently, with a default. |
| Layer | A group of rules from one source. Six layers, from most general to most specific: principles, language, company, department, team, application. |
| More general, more specific | The direction between layers. The more specific layer wins, but it may never loosen a floor. Never say "higher" or "lower". |
| Principles layer | Layer 1: rules true for all code. Written by harnesswright. IDs start with `CORE`. |
| Language layer | Layer 2: rules for one language, with a sub-layer per framework. Written by harnesswright. IDs start with the language, such as `JAVA` or `JAVA-SPRING`. |
| Company, department, team layers | Layers 3 to 5: optional rules a large company adds for its teams. The company picks each name, which only prefixes the IDs so they never clash, such as `COMP-ACME`. |
| Application layer | Layer 6: the rules of one application, mostly learned from its code. IDs start with `APP`. |
| Application | One codebase with one `.harness/` folder at its root. |
| `.harness/` folder | The folder in an application's repository that tells the skills about that application, like `.github/`. |
| `harnesswright init` | The command that sets up an application: it detects the language and tools, learns how existing code is written, and writes the `.harness/` folder for a person to confirm. |
| Profile | `.harness/profile.yaml`: the application's language, test tools and the layers it uses. |
| Stacks | Parts of one application in different languages, such as Java and Angular, under one owner. Each stack has its own language and framework layers; layers 3 to 6 are shared. |
| Area | One topic of rules, such as naming (`NAME`), design (`DSGN`) or tests (`TEST`). |
| Standard | The file of rules for one area in one layer. |
| Rulebook | All standards of all layers. |
| Resolved standards | The one list of rules that applies to a run, after the layers are combined. |
| Planned item | An epic or a feature: work that gets a functional plan and a technical design. |
| Known breach | Existing code that already breaks a floor, recorded and confirmed by the application owner. It is reported, not blocked. |
| Waiver | A dated, approved permission for one application or one story not to follow one rule that is not a floor. |
| Contract | The fixed shape of a file one role hands to another. |
| Panel | Several independent agents that vote on one judgment. |
| Capability | Access to an outside system, provided by an MCP server, a CLI or nothing. |
