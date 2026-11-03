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
never rule text. Every role in the run reads it. Claims and verdicts record one value: the hash of `rules.md`
itself.

## Functional plan

Written by the functional planner for a planned item (an epic or a feature).

```yaml
---
id: P-order-retry
status: draft               # draft | approved | rejected
gaps-accepted-by: none      # who accepted the plan's gaps, and when; "none" when it has no gaps
---
```

Sections: **Goal** (one paragraph) · **In scope** · **Out of scope**, with reasons · **Acceptance criteria**,
numbered `AC-1`, `AC-2`, …, each testable · **Non-functional targets**, numbered `NFR-1`, `NFR-2`, … (latency,
throughput, memory, CPU, availability), each in one of the states below · **Gaps** · **Risks**.

**One rule for requirements.** Every acceptance criterion and every target not marked "not applicable" is a
*requirement*. Each requirement names the test types it requires, from the process setting `test-types`. In a plan,
the functional planner proposes them and they are approved with the plan. A story with no plan takes them from the
same setting. Everything below that says "requirement" means both kinds.

**Performance targets.** The functional planner asks the person for each target and never reads monitoring tools.
No number is ever invented. Each target is in one of four states:

- **Exact**, for example "p95 under 200 ms". Its test must pass.
- **Estimated**: a ballpark the planner turns into a range and marks `estimated`. Its test must exist, but a missed
  range is a warning, not a fail.
- **Unknown**: the requirement is a baseline benchmark, test type `performance`. The test measures the target's
  metric in the test environment, saves the figure, and fails when a later change makes that metric worse by more
  than the process setting `baseline-tolerance`.
- **Not applicable**: not a requirement.

**One rule for gaps.** An unknown target ("performance not verified") and a not-applicable target are *gaps*. The
plan lists each gap with its reason under **Gaps**, and a person accepts them; `gaps-accepted-by` records who and
when. This holds at every tier: a plan with gaps waits for a person even where its tier has no human plan gate. The
plan reviewer fails a plan with a gap that is not listed or not accepted. A T3 plan needs at least one performance
requirement; a baseline benchmark counts.

A later planned item replaces an estimate or a baseline with a real number.

## Technical design

Written by the technical designer for the same planned item, after the functional plan is written. The plan
reviewer reviews both together.

```yaml
---
id: D-order-retry
plan: P-order-retry
status: draft               # draft | approved | rejected
---
```

Sections: **Approach** (one paragraph) · **Design elements**, numbered `TD-1`, `TD-2`, …, each naming the
criteria or targets it serves (`serves: [AC-1, NFR-2]`) · **Test data**: the data each test type needs, with its
shape, volume and sensitive fields · **Decisions** (links to decision records) · **Risks**.

The test writer builds the test data: fixtures for unit and integration tests, and generated data for performance
tests, shaped like the traffic the person describes. Test data follows the standards area `ITEST`
([03 · Standards](03-standards.md)).

The plan reviewer checks that the two match: every element serves at least one requirement, and every
requirement is served by at least one element.

## Story

```yaml
---
id: S02
plan: P-order-retry         # or "none" for a change with no plan
depends-on: [S01]
covers: [AC-1, AC-3, NFR-1, TD-2]   # the criteria, targets and design elements this story delivers
tests: {AC-1: [unit], AC-3: [unit, integration], NFR-1: [performance]}   # test types for each requirement
waivers: []                 # story-scoped waivers: rule ID, reason, end date, approver
---
```

Sections: **What** (one paragraph) · **Request** (only when `plan` is `none`: the request, quoted) ·
**Acceptance criteria** (testable, each with its required test types) · **Targets** (each target it covers,
quoted from the plan with its state and number or range) · **Out of scope** · **Tasks** (optional,
only when the team tracks tasks).

A story with a plan uses the plan's IDs. A story with `plan: none` numbers its own criteria `AC-1`, `AC-2`, …,
lists them in `covers`, and keys `tests` by them.

A story may be tests only, such as "add contract tests for API X". A story-scoped waiver is recorded in `waivers`
before work starts, approved as [03 · Standards](03-standards.md) says, and cited in the claims. It lives only in
the story, never in `rules.md`, so the story judge checks each waiver the claims cite against the story.

Where a story comes from depends on the tier. For T2 and T3 the story writer splits the plan. For T0 and T1 there
is no plan: triage writes a single story, with `plan: none`, straight from the request, and the story judge checks
the change against that story's own acceptance criteria.

A story is small enough to review in one sitting. The alignment judge checks that every requirement and
design element is covered by at least one story, that each story's `tests` include every test type the plan
requires for each requirement it covers, and that no story does anything the plan or the design does not ask for.

## Claims

Written by the implementer when a story is finished.

Sections: **Request** (the story, quoted) · **Requirements**: for each requirement the story covers, what was
done and the evidence (`file:line`, test name, command and output), and for each required test type the test that
proves it, with the measured figure for each performance target · **Standards**: the hash of `rules.md`, the rules
applied, by ID, and each waiver used · **Out of scope**, with reasons · **Files changed**, each with its line
count · **Not verified**: anything the implementer could not prove.

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
rules: 9b1e…                # hash of the rules.md the judge read
result: pass                # pass | fail
votes: {approve: 2, reject: 1}
blockers: []                # confirmed blockers; any entry forces fail
warnings: []                # missed estimated ranges; never forces fail
---
```

Body: each claim, checked or refuted with evidence; then what must change for a pass. The story judge fails a
requirement whose required test type has no test. It reads each target's state from the story: a missed exact
target or a failed baseline benchmark is a blocker, and a missed `estimated` range goes under `warnings`.

A verdict applies to the content of the commit it names, outside the run folder. A later commit keeps the verdict
valid only if it changes nothing outside `.harness/runs/`, which holds the verdict files themselves and the
removal of the run folder before merge. The coordinator checks this with
`git diff --name-only <commit> HEAD -- . ':(exclude).harness/runs'`: any file listed means the judged content
changed, and the change needs a new verdict.

## Decision record

For tier 3 changes, the technical designer writes one record per decision: **Context** · **Options considered** ·
**Decision** · **Consequences**. Records are kept with the technical design.
