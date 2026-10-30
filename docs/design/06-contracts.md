# 06 · Contracts

A contract is the fixed shape of what one role hands to another. Agents can be swapped; contracts cannot, because
every panel, judge and resumed run depends on them. Each contract is a Markdown file with YAML frontmatter. The
templates will live in `contracts/`.

## Where contracts are kept

Each run has a folder, `.harness/runs/<run-id>/`, on the change's branch:

```text
.harness/runs/2026-10-30-order-retry/
├── triage.md
├── plan.md
├── decisions/
├── stories/S01.md, S02.md, …
├── claims/S01.md, …
├── findings/<stage>/<agent>.md
├── votes/<stage>.md
├── verdicts/S01.md, …, feature.md
└── log.md
```

Whether the run folder stays in the repository after merge is an open question (see [09 · Roadmap](09-roadmap.md)).

## Triage

```yaml
---
change-type: feature        # docs | config | bugfix | refactor | dependency | feature | incident
tier: T2                    # T0 | T1 | T2 | T3
reasons: [touches public API of orders module]
pipeline: feature-t2
---
```

## Plan

```yaml
---
id: P-order-retry
status: draft               # draft | approved | rejected
---
```

Sections: **Goal** (one paragraph) · **In scope** · **Out of scope**, with reasons · **Non-functional targets**
(latency, throughput, memory, CPU, availability, each with a number or "not applicable") · **Risks** ·
**Acceptance criteria** (numbered, each one testable) · **Decisions** (links to decision records).

Performance and load tests are written against the non-functional targets. A plan without them cannot be approved
for a T3 change.

## Story

```yaml
---
id: S02
plan: P-order-retry
depends-on: [S01]
covers: [AC-1, AC-3]        # the plan's acceptance criteria this story delivers
---
```

Sections: **What** (one paragraph) · **Acceptance criteria** (testable, each linked to the plan) · **Tests
expected** (unit, integration, performance as relevant) · **Out of scope**.

A story is small enough to review in one sitting. The alignment judge checks that every plan criterion is covered
by at least one story and that no story does anything the plan does not ask for.

## Claims

Written by the implementer when a story is finished. The format follows Stratum's judge claims.

Sections: **Request** (the story, quoted) · **Requirements**: for each acceptance criterion, what was done and the
evidence (`file:line`, test name, command and output) · **Standards** applied, by rule ID, with any exception and
its reason · **Out of scope**, with reasons · **Files changed**, each with its line count · **Not verified**:
anything the implementer could not prove.

## Finding

```yaml
---
id: F-007
stage: story-review
author: security-reviewer
severity: blocker           # blocker | major | minor | note
status: confirmed           # confirmed | plausible | refuted
rule: CORE-SEC-04           # the rule it breaks, if any
location: src/orders/RetryClient.java:42
---
```

Body: what is wrong, the evidence, and the smallest fix.

## Vote

```yaml
---
stage: plan-review
voter: plan-reviewer-2
model-class: deep
vote: reject                # approve | reject
findings: [F-003, F-004]
---
```

Body: one paragraph of reasoning, written before the voter sees any other vote.

## Verdict

```yaml
---
subject: S02                # a story ID, or "feature"
commit: 3f9c2e1             # the exact commit judged
result: pass                # pass | fail
votes: {approve: 2, reject: 1}
blockers: []                # confirmed blockers; any entry forces fail
---
```

Body: each claim, checked or refuted with evidence; then what must change for a pass. A verdict applies only to
the commit it names. Any new commit needs a new verdict.

## Decision record

For tier 3 changes, the architect writes one record per decision: **Context** · **Options considered** ·
**Decision** · **Consequences**. Records are kept with the plan.
