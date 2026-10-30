# 04 · Roles

A role is one job in the engineering team. Each role is written once, in the core, and reads the resolved
standards of the repository it works in. A role's instructions name the standards it applies by rule ID or area.
They never repeat the rules.

## Model classes

Roles ask for a model class, not a specific model. The repository profile maps each class to a concrete model,
so a newer model can be adopted by changing one line.

| Class | Use |
|---|---|
| `deep` | Planning, architecture, judging, security, adjudicating disputes |
| `standard` | Implementing, writing tests, reviewing, writing stories |
| `fast` | Triage, mechanical checks, summarising |

A panel should mix models where possible. Voters that are the same model with the same prompt and context tend to
make the same mistake, so their agreement proves less.

## The roles

| Role | Purpose | Reads | Produces | Model class | Writes code |
|---|---|---|---|---|---|
| **Coordinator** | Runs the pipeline: starts roles, counts votes, enforces limits, escalates | Process config, run folder | Run log, escalations | `standard` | No |
| **Triage** | Chooses the change type and risk tier, and so the pipeline | Request, diff or issue, repository map | Triage record | `fast`, `deep` if uncertain | No |
| **Architect** | Makes and records design decisions for tier 3 changes | Request, codebase, standards | Decision records | `deep` | No |
| **Planner** | Writes a plan: goal, scope, non-functional targets, risks, acceptance criteria | Request, decisions, standards (`PLAN`) | Plan | `deep` | No |
| **Plan reviewer** | Reviews a plan and votes on it | Plan, request, standards | Findings, vote | `deep` | No |
| **Story writer** | Splits an approved plan into small, independent, testable stories with an order | Plan | Stories | `standard` | No |
| **Alignment judge** | Checks that the stories cover the plan, with nothing missing and nothing extra | Plan, stories | Verdict | `deep` | No |
| **Implementer** | Builds one story: code, tests and documentation, then writes the claims | Story, standards, codebase | Change, claims | `standard` | Yes |
| **Tester** | Writes or reviews unit, integration and performance tests, and proves each test fails when its code breaks | Story, change, standards (`TEST`, `ITEST`, `PERF`) | Tests, findings | `standard` | Tests only |
| **Code reviewer** | Reviews design, naming, simplicity and documentation | Change, story, standards | Findings, vote | `standard` or `deep` | No |
| **Security reviewer** | Reviews against the `SEC` rules and runs the security tools | Change, standards, tool results | Findings, vote | `deep` | No |
| **Story judge** | Verifies that each claim is true and the story is done | Story, claims, change, tool results | Verdict | `deep` | No |
| **Feature judge** | Verifies that the delivered stories together meet the plan | Plan, all story verdicts, change | Verdict | `deep` | No |
| **Scenario tester** | Invents a realistic use case, prepares its data, runs it end to end, and reports how the system behaved | Plan, running system | Scenario report | `standard` | Test data and scripts only |
| **Release reviewer** | Checks operational readiness: observability, migrations, flags, rollback, runbooks | Change, standards (`OPS`) | Findings, vote | `deep` | No |
| **Curator** | Turns repeated human corrections into proposed rules in the right layer | Escalations, review history | Rule proposals | `deep` | No |

## What every role must do

These duties come from Stratum's agent rules and apply to every role:

1. **Report only what you verified.** Each statement cites a command and its output, a test, or a `file:line`.
   Anything not verified is labelled as such.
2. **Done means proven.** A role never calls work done without evidence for each part.
3. **Do only what was asked.** A role adds nothing the story or request did not call for. Ideas for extra work go
   in the report as proposals.
4. **Never weaken a safeguard.** No skipped tests, suppressed checks or loosened rules.
5. **Keep secrets and personal data out** of every file, log, message and contract.
6. **Do not stop silently.** When blocked, try another legitimate route or ask one clear question.

## Independence

Independence is what makes a vote worth anything:

- A reviewer or judge never sees the implementer's reasoning or conversation. It sees only the contracts (story,
  claims), the change itself and tool results.
- Voters on one panel do not see each other's votes until all have voted.
- The judge role is never combined with any other role on the same change.
- A finding is promoted from *plausible* to *confirmed* only by evidence, never by agreement. See
  [05 · Process](05-process.md).

## Access by role

| Role | Read code | Write code | Run tools and tests | Outside systems |
|---|---|---|---|---|
| Triage, planner, architect, story writer | Yes | No | Read-only commands | Read the issue tracker |
| Implementer, tester | Yes | Yes, in its own worktree | Yes | None by default |
| Reviewers, judges | Yes | No | Yes, read-only | Read the code host |
| Scenario tester | Yes | Test data and scripts only | Yes, in a disposable environment | Test environments only |
| Coordinator | Yes | Run folder only | No | Code host: comments and PRs, if granted |

No role has write access to production. See [07 · Repository profile](07-repo-profile.md) for how capabilities
are granted.
