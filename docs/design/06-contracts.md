# 06 · Contracts

A contract is the fixed shape of what one role hands to another. Agents can be swapped; contracts cannot, because
every panel, judge and resumed run depends on them. Each contract is a Markdown file, with YAML frontmatter where
its section below shows one. The templates will live in `contracts/`.

## Where contracts are kept

Each run has a folder, `.harness/runs/<run-id>/`, on the change's branch:

```text
.harness/runs/2026-10-30-order-retry/
├── triage.md
├── rules.md
├── rules-text-<skill>.md
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

## Approvals

Gaps, estimated ranges, story-scoped waivers and open proof items each need a person's approval. Each has an ID: a
gap or an estimated range has its requirement's ID (`AC-1`, `NFR-2`), a story-scoped waiver its rule ID, and an open
proof item its own (`OP-1`, `OP-2`, … in the claims). An approval counts only when the person gave it from their
own account: a review or a comment in the pull request, naming the IDs it covers, with the story ID for a waiver
or an open proof item (`S02 OP-1`). A name typed into a contract does not count.

Every vote and verdict has an **Approvals** part: each item it relies on, by ID, with the review or comment cited,
or `not approved`, or `not verified` when the role cannot look the approval up. Both of the last two count as
missing. A vote cannot approve, and a verdict cannot pass, while an item it relies on is missing. A part with no
item says `none`.

- A plan reviewer's vote relies on the plan's gaps and estimated ranges.
- A story judge's verdict relies on every open proof item in the claims, each story-scoped waiver the claims cite,
  and the gaps and estimated ranges of the criteria and targets the story covers, from its plan or its own.

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
never rule text. Every role in the run reads it. Beside it, the standards reader writes one rules text per skill,
`rules-text-<skill>.md`, and records the hash of each in `rules.md`. A rules text ends with a read-back block: the
rule count, and the ID and title of its last rule. Claims and verdicts record the hash of `rules.md` and quote each
read-back block, as the claims contract says.

## Functional plan

Written by the functional planner for a planned item (an epic or a feature).

```yaml
---
id: P-order-retry
status: draft               # draft | approved | rejected
---
```

Sections: **Goal** (one paragraph) · **In scope** · **Out of scope**, with reasons · **Acceptance criteria**,
numbered `AC-1`, `AC-2`, …, each testable · **Non-functional targets**, numbered `NFR-1`, `NFR-2`, … (latency,
throughput, memory, CPU, availability), each in one state · **Gaps** · **Risks**.

| Target state | Holds | Requirement |
|---|---|---|
| `exact` | A number, such as "p95 under 200 ms" | Yes. Its test must pass. |
| `estimated` | A range the person gave or confirmed, approved | Yes. A missed range is a `minor` finding. |
| `unknown` | No measured figure. A target relative to a figure nobody measured is unknown. | Yes, as a baseline benchmark: the test writer measures the figure in the test environment and saves it, and the test fails when a later change makes it worse by more than the process setting `baseline-tolerance`, a percentage |
| `not applicable` | Nothing | No |
| `not testable here` | Nothing: the team has no performance test type | No |

No number is ever invented. The functional planner asks the person for each target.

**One rule for requirements.** Every acceptance criterion and every target that is not `not applicable` or `not
testable here` is a *requirement*. Each requirement names the test types it requires, only from the process setting
`test-types`. Everything below that says "requirement" means both kinds.

Each acceptance criterion gives its statement and its test types. Each target gives what it measures, its state,
its number (`exact`) or range (`estimated`), and its test types.

**Gaps** lists, each with its reason: every target that is `unknown`, `not applicable` or `not testable here`, and
every acceptance criterion with no test type. A person approves each gap, at every tier, even where the tier has
no human plan gate. The plan reviewer checks that each gap is listed with its reason and approved.

Performance and load tests are written against the non-functional targets. A T3 plan whose team has a performance
test type cannot be approved without at least one performance requirement; a baseline benchmark counts.

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
criteria or targets it serves (`serves: [AC-1, NFR-2]`) · **Test data**: for each test type, the data its tests
need (shape, volume and any sensitive fields), which the test writer builds · **Decisions** (links to decision
records) · **Risks**.

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
targets: {NFR-1: estimated} # exact | estimated | unknown | not applicable | not testable here
waivers: []                 # story-scoped waivers: rule ID, reason, end date, approving accounts
---
```

Sections: **What** (one paragraph) · **Request** (only when `plan` is `none`: the request, quoted) ·
**Acceptance criteria** (testable, each with its required test types) · **Targets** (only when `plan` is `none`:
each target with its state, as in the functional plan) · **Gaps** (only when `plan` is `none`: each target that is
`unknown`, `not applicable` or `not testable here`, with its reason) · **Out of scope** · **Tasks** (optional, only
when the team tracks tasks).

A story with a plan uses the plan's IDs and the plan's state for each target. A story with `plan: none` numbers its
own criteria `AC-1`, `AC-2`, … and targets `NFR-1`, `NFR-2`, …, lists them in `covers`, and keys `tests` and
`targets` by them. Triage asks the person whether the change has any targets; each one named takes the team's
performance test type. Its criteria take the test types the process setting `default-test-types` gives its change
type. The story judge checks its gaps as the plan reviewer checks a plan's.

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

Written by the claims writer when a story is finished.

Sections: **Request** (the story, quoted) · **Requirements**: for each requirement the story covers, what was
done and the evidence (`file:line`, test name, command and output), and for each required test type the test that
proves it, or the `OP-n` that stands in for it · **Open proof items** · **Standards** · **Out of scope**, with
reasons · **Files changed**, each with its line count · **Not verified**: anything that could not be proven.

**Open proof items** are proof that cannot be made in the pull request, such as a full load run on staging or tests
in a repository the agent cannot reach. Each one says what is unproven (with the requirement ID and test type when
it stands in for a test), where and when the proof will come from, and who owns it. Each is numbered `OP-1`,
`OP-2`, … The claims writer also lists them at the top of the pull request description. Nothing tracks an open
proof item after merge.

**Standards** holds:

- the hash of `rules.md`;
- each skill run, in the order it ran, with its version, the hash of its release `SKILL.md` and the read-back block
  of its rules text, quoted exactly, marked `not verified` where the rules text was written by reading;
- the ID and title of each change applied (an override, binding or tightening in a rules text), quoted exactly;
- the rules applied, by ID, and each waiver used.

A script compares the skills, read-back blocks and changes, character for character, with the rules texts and the
job in the roles file. The story judge rebuilds the rules texts and fails on any difference.

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

Body: one paragraph of reasoning, written before the voter sees any other vote · **Approvals** (see Approvals).

## Verdict

```yaml
---
subject: S02                # a story ID, or "feature"
commit: 3f9c2e1             # the exact commit judged
rules: 9b1e…                # hash of the rules.md the judge read
result: pass                # pass | fail
votes: {approve: 2, reject: 1}
blockers: []                # confirmed blockers; any entry forces fail
---
```

Body: **Claims**: each claim, checked or refuted with evidence · **Approvals** (see Approvals) · **Standards**:
each skill the judge ran, in order, with its version, hash and read-back block, and each change applied, as in the
claims · **To pass**: what must change for a pass. The story judge fails a requirement whose required test type has
no test, unless that test is an approved open proof item.

A verdict applies to the content of the commit it names, outside the run folder. A later commit keeps the verdict
valid only if it changes nothing outside `.harness/runs/`, which holds the verdict files themselves and the
removal of the run folder before merge. The coordinator checks this with
`git diff --name-only <commit> HEAD -- . ':(exclude).harness/runs'`: any file listed means the judged content
changed, and the change needs a new verdict.

## Decision record

For tier 3 changes, the technical designer writes one record per decision: **Context** · **Options considered** ·
**Decision** · **Consequences**. Records are kept with the technical design.
