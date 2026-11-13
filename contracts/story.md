---
id: S<NN>
plan: P-<item>              # or none for a change with no plan
depends-on: [<story ID>]    # [] when none
covers: [<AC, NFR or TD ID>]          # the criteria, targets and design elements this story delivers
tests: {<AC or NFR ID>: [<test type>]}   # test types for each requirement it covers
targets: {<NFR ID>: <state>}           # exact | estimated | unknown | not applicable | not testable here; {} when none
waivers: []                 # story-scoped waivers, each {rule: <rule ID>, reason: <reason>, until: <YYYY-MM-DD>, approved by: <account>}
---

## What

<one paragraph>

## Request

<!-- only when plan is none -->

> <the request, quoted>

## Acceptance criteria

### AC-1

- **Criterion:** <a testable statement>
- **Test types:** [<test type>]

## Targets

<!-- only when plan is none -->

### NFR-1

- **Measure:** <measure>     # latency | throughput | memory | CPU | availability
- **State:** <state>         # exact | estimated | unknown | not applicable | not testable here
- **Target:** <what is measured; the number when exact, the range when estimated>
- **Test types:** [<test type>]

## Gaps

<!-- only when plan is none -->

- <NFR ID>: <reason>

## Out of scope

- <what the story does not do>: <reason>

## Tasks

<!-- optional: only when the team tracks tasks -->

- <task>
