# 04 · Roles

A role is one part of the agent team, such as story judge. Each role is written once, in the core, and reads the
resolved standards of the repository it works in. A role's instructions name the standards it applies by rule ID or
area. They never repeat the rules.

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

[v2/roles.md](../../v2/roles.md) is the one list of roles, with each role's details. A rule's Applies to, a
template's `metadata.roles` and a pipeline step name roles and jobs as that file requires.

## Jobs

- A **job** is the ordered list of skills one pipeline step runs, and the role or roles that step's agent acts
  as. [v2/roles.md](../../v2/roles.md) is the only list of jobs. A pipeline step names a job from it.
- Each job names exactly one skill whose areas are `rest`: every area of its roles, from any layer, that no other
  skill of the job lists. It is the skill that produces the job's main output. A one-skill job is `rest` by itself.
- A skill belongs to one job, and its roles are that job's roles. A skill that two different pipeline steps would
  run is its own role with its own one-skill job, run as its own pipeline step. Jobs never share a skill.
- A job splits into several skills only where its work runs in steps.

## What every role must do

These duties apply to every role:

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
| Triage, functional planner, technical designer, story writer, UAT handoff | Yes | No | Read-only commands | Read the issue tracker |
| Implementer, test writer | Yes | Yes, in its own worktree | Yes | None by default |
| Standards reader, toolchain check, claims writer | Yes | Run folder only | Yes | None |
| Reviewers, judges, verifier, adjudicator, rule keeper | Yes | No | Yes, read-only | Read the code host |
| QA tester | Yes | Test data and scripts only | Yes, in a disposable environment | Test environments only |
| Coordinator | Yes | Run folder only | No | Code host: comments and PRs, if granted |
| Rule writer, skill designer, curator | Yes | Rules, skills, evals and rule requests in harnesswright, on a branch | Yes | None by default |

No role has write access to production. See [07 · Repository profile](07-repo-profile.md) for how capabilities
are granted.
