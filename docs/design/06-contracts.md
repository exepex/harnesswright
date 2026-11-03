# 06 · Contracts

A contract is the fixed shape of what one role hands to another. Agents can be swapped; contracts cannot, because
every panel, judge and resumed run depends on them. Each contract is a Markdown file with YAML frontmatter. The
templates will live in `contracts/`.

## Where contracts are kept

Each run has a folder, `.harness/runs/<run-id>/`, on the change's branch:

```text
.harness/runs/2026-10-30-order-retry/
├── triage.md
├── rules.md
├── functional-plan.md
├── design.md
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

## Resolved standards

`rules.md`, written once by the standards reader at the start of the run. Its inputs, steps and fields are defined
in [03 · Standards](03-standards.md), "Resolving the rules for an application". It holds rule IDs and fingerprints,
never rule text. Every role in the run reads it.

## Functional plan

Written by the functional planner for a planned item (an epic or a feature).

```yaml
---
id: P-order-retry
status: draft               # draft | approved | rejected
---
```

Sections: **Goal** (one paragraph) · **In scope** · **Out of scope**, with reasons · **Acceptance criteria**,
numbered `AC-1`, `AC-2`, …, each testable and each naming the test types it requires, from the process setting
`test-types` · **Non-functional targets**, numbered `NFR-1`, `NFR-2`, … (latency, throughput, memory, CPU,
availability, each with a number or "not applicable") · **Risks**.

Performance and load tests are written against the non-functional targets. A functional plan without them cannot
be approved for a T3 change.

## Technical design

Written by the architect for the same planned item, after the functional plan is approved.

```yaml
---
id: TD-order-retry
plan: P-order-retry
status: draft               # draft | approved | rejected
---
```

Sections: **Approach** (one paragraph) · **Design elements**, numbered `TD-1`, `TD-2`, …, each naming the
criteria or targets it serves (`serves: [AC-1, NFR-2]`) · **Decisions** (links to decision records) · **Risks**.

A design element that serves no criterion or target is out of scope. The plan reviewer checks that the functional
plan and the technical design match.

## Story

```yaml
---
id: S02
plan: P-order-retry         # or "none" for a change with no plan
depends-on: [S01]
covers: [AC-1, AC-3, TD-2]  # the criteria and design elements this story delivers; empty when plan is "none"
tests: {AC-1: [unit], AC-3: [unit, integration]}   # required test types for each criterion
waivers: []                 # story-scoped waivers: rule ID, reason, end date, approver
---
```

Sections: **What** (one paragraph) · **Request** (only when `plan` is `none`: the request, quoted) ·
**Acceptance criteria** (testable, each linked to the plan when there is one, each with its required test types)
· **Out of scope** · **Tasks** (optional, only when the team tracks tasks).

A story may be tests only, such as "add contract tests for API X". A story-scoped waiver is recorded in `waivers`
before work starts, approved as [03 · Standards](03-standards.md) says, and cited in the claims.

Where a story comes from depends on the tier. For T2 and T3 the story writer splits the plan. For T0 and T1 there
is no plan: triage writes a single story, with `plan: none`, straight from the request, and the story judge checks
the change against that story's own acceptance criteria.

A story is small enough to review in one sitting. The alignment judge checks that every plan criterion is covered
by at least one story, that every design element is covered, and that no story does anything the plan or the
design does not ask for.

## Claims

Written by the implementer when a story is finished.

Sections: **Request** (the story, quoted) · **Requirements**: for each acceptance criterion, what was done and the
evidence (`file:line`, test name, command and output), and for each required test type the test that proves it ·
**Standards**: the fingerprint of `rules.md`, and each waiver used, by rule ID · **Out of scope**, with reasons ·
**Files changed**, each with its line count · **Not verified**: anything the implementer could not prove.

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
rules: 9b1e…                # fingerprint of the rules.md the judge read
result: pass                # pass | fail
votes: {approve: 2, reject: 1}
blockers: []                # confirmed blockers; any entry forces fail
---
```

Body: each claim, checked or refuted with evidence; then what must change for a pass. The story judge fails a
criterion whose required test type has no test.

A verdict applies to the content of the commit it names, outside the run folder. A later commit keeps the verdict
valid only if it changes nothing outside `.harness/runs/`, which holds the verdict files themselves and the
removal of the run folder before merge. The coordinator checks this with
`git diff --name-only <commit> HEAD -- . ':(exclude).harness/runs'`: any file listed means the judged content
changed, and the change needs a new verdict.

## Decision record

For tier 3 changes, the architect writes one record per decision: **Context** · **Options considered** ·
**Decision** · **Consequences**. Records are kept with the technical design.
