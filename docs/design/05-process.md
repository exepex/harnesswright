# 05 · Process

Process decides which roles run for a change, in what order, how many vote and when to stop. It holds names and
numbers only. A repository can change the numbers in its profile.

## Change types

Triage gives every change one type. The type chooses the shape of the pipeline.

| Type | Example | Shape |
|---|---|---|
| `docs` | README, guide, comments only | Judge only |
| `config` | Build file, YAML, properties | Implement, toolchain, review, judge |
| `bugfix` | Wrong behaviour | Reproduce with a failing test first, then implement, review, judge |
| `refactor` | Same behaviour, better structure | Prove behaviour unchanged (tests pass before and after), review, judge |
| `dependency` | Version upgrade | Read migration notes, implement, full test suite, security scan, judge |
| `feature` | New behaviour | Plan (tier 3), stories, implement, review, judge |
| `incident` | Production problem | Diagnose from evidence, smallest safe fix, review, judge, follow-up story |

## Risk tiers

Triage also gives every change a tier. The tier sets how many agents take part.

| Tier | Typical change | Planning | Reviewers | Story judges | Extra |
|---|---|---|---|---|---|
| **T0** | Text only, no behaviour | None; triage writes one story from the request | None | 1 | None |
| **T1** | Small, isolated code or configuration | None; triage writes one story from the request | 1 code | 1 | None |
| **T2** | A feature or fix inside one module | Short plan by the functional planner, no panel; story writer splits it | Code, tests, security | Panel of 3 | Integration tests |
| **T3** | Several modules, public API, security, data, performance-critical paths | Plan panel of 3, human gate | Code, tests, security, release | Panel of 3 | Alignment judges, feature judges, QA testers, performance tests |

Rules for triage:

- When unsure between two tiers, choose the higher one.
- Any change to authentication, authorisation, cryptography, secrets handling, personal data or a public API is at
  least T2.
- A human may raise a tier at any time. Lowering a tier needs a human.

## Facts are checked; judgments are voted on

Before any reviewer or judge runs, the toolchain from the language profile runs: build, formatter, linter, tests,
coverage, static security analysis and dependency scanning. Its results are facts. A failed check sends the change
back to the implementer, with no vote.

Panels vote only on judgments: is this plan sound, do these stories cover the plan, is this design simple enough,
is this story really done.

## Findings

Every reviewer and judge reports findings in the finding contract. Each finding has a severity and a status.

| Severity | Meaning |
|---|---|
| `blocker` | Must be fixed before approval: wrong behaviour, a broken floor, a security flaw, a false claim |
| `major` | Should be fixed in this change; approval needs a stated reason to defer it |
| `minor` | Worth fixing; does not block |
| `note` | Observation or proposal; no action required |

| Status | Meaning |
|---|---|
| `confirmed` | Reproduced by evidence: a failing test, a tool result, a trace, or an exact `file:line` that shows it |
| `plausible` | Argued but not yet proven |
| `refuted` | Disproved by evidence |

## Voting

Each panel member votes `approve` or `reject` on its own, without seeing the others, and gives its findings.

A panel **approves** when both of these hold:

1. A majority of the panel votes `approve`.
2. No finding is a `confirmed` `blocker`.

So a single proven blocker vetoes approval, whatever the count. An unproven blocker (`plausible`) does not veto.
It goes to a verifier, a different agent that tries to confirm or refute it with evidence. Its result settles the
finding.

A panel **deadlocks** when votes are split with no majority, or when a verifier cannot settle a blocker. A
deadlock goes to an adjudicator, a single `deep` agent that sees all findings and evidence. If the adjudicator
cannot decide with evidence, the coordinator escalates to the human.

## Rounds and limits

| Limit | Default | When reached |
|---|---|---|
| Rework rounds per story | 3 | Escalate to the human |
| Plan revision rounds | 2 | Escalate to the human |
| Token budget per change | Set per tier in the profile | Stop and report what is done and what is not |
| Wall-clock time per stage | Set per tier in the profile | Stop and report |
| Each rules text (one per skill and stack) | 30,000 characters; an application may raise it to at most 60,000 ([07](07-repo-profile.md)) | Park the item with an open item that lists sizes per layer and area |

## Escalation

An escalation is one clear question for the human, with:

- what was being decided,
- the options and the evidence for each,
- the agents' recommendation, if they have one,
- what is blocked until the human answers.

The coordinator never escalates with "please review" alone.

## Parallel work

Stories with no dependency on each other can be implemented in parallel, each in its own git worktree. The story
writer records dependencies, and the coordinator starts a story only when the stories it depends on have passed.
Merge conflicts go back to the implementer of the later story.

## Defaults a repository can change

Panel sizes, model classes per role, tier thresholds, round limits, budgets, extra human gates and which optional
roles run. A repository cannot remove the merge gate, the escalation gate, the veto of a confirmed blocker, or the
toolchain checks.
