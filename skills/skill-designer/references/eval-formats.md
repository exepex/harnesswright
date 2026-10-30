# Eval formats

Adapted from `references/schemas.md` of Anthropic's skill-creator (`anthropics/skills@ca45fc4`, Apache-2.0).
Changed by harnesswright: evals live under `evals/skills/<name>/`, trigger queries carry IDs, and host-specific
fields (tool names, model names, viewer fields) are removed so results compare across hosts.

Every skill's evals live in `evals/skills/<name>/`, where `<name>` is the skill's name:

```text
evals/skills/<name>/
├── triggers.json      Trigger evals
├── tasks.json         Task evals
├── files/             Input files the tasks use
└── checks/            Scripts that check expectations
```

Results are written by the eval runner, per host. Their format is defined with the runner.

## triggers.json

```json
{
  "skill_name": "unit-test-writer",
  "queries": [
    {"id": "t01", "query": "the OrderService in src/orders has no tests at all, can you add some for the discount logic", "should_trigger": true},
    {"id": "t02", "query": "set up a k6 load test for the checkout endpoint, we need 200 rps", "should_trigger": false}
  ]
}
```

| Field | Meaning |
|---|---|
| `skill_name` | Matches the skill's `name` |
| `queries[].id` | Unique within the file, never reused |
| `queries[].query` | The request, as a person would type it |
| `queries[].should_trigger` | `true` if the host should load the skill for this request |

A query passes when its trigger rate over repeated runs is at least 0.5 and `should_trigger` is `true`, or below
0.5 and `should_trigger` is `false`. Trigger accuracy is the share of queries that pass.

## tasks.json

```json
{
  "skill_name": "unit-test-writer",
  "tasks": [
    {
      "id": 1,
      "name": "discount-rules-tests",
      "prompt": "Add unit tests for DiscountCalculator in files/DiscountCalculator.java",
      "expected_output": "A test file whose tests cover each discount rule, named after scenario and outcome",
      "files": ["files/DiscountCalculator.java"],
      "expectations": [
        {"text": "Each discount rule has at least one test", "check": "judge"},
        {"text": "Every test name states the scenario and the outcome", "check": "judge"},
        {"text": "The tests compile and pass", "check": "checks/run_tests.sh"}
      ]
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `tasks[].id` | Unique integer |
| `tasks[].name` | Short descriptive name, also used for the result folder |
| `tasks[].prompt` | The task, as a person would give it |
| `tasks[].expected_output` | A plain description of success |
| `tasks[].files` | Input files, relative to `evals/skills/<name>/` |
| `tasks[].expectations[].text` | One checkable statement |
| `tasks[].expectations[].check` | `judge` for the grader, or the path of a script in `checks/` |

A check script receives the run's output folder as its only argument and exits with 0 when the expectation holds.
It follows `HW-PORT-04`: Python 3 standard library or POSIX `sh`, no network calls, deterministic.

A task passes when all its expectations pass. The task pass rate is the share of tasks that pass.

## grading.json

Written by the grader for one run, next to the run's output folder.

```json
{
  "expectations": [
    {"text": "Each discount rule has at least one test", "passed": true, "evidence": "DiscountCalculatorTest.java:12-58 has one test per rule: seasonal, loyalty, bulk"},
    {"text": "The tests compile and pass", "passed": false, "evidence": "checks/run_tests.sh exited 1: 'cannot find symbol LoyaltyTier'"}
  ],
  "summary": {"passed": 1, "failed": 1, "total": 2, "pass_rate": 0.5},
  "claims": [
    {"claim": "All three discount rules are covered", "type": "factual", "verified": true, "evidence": "Rules at DiscountCalculator.java:20,31,44"}
  ],
  "eval_feedback": {
    "suggestions": [
      {"expectation": "The tests compile and pass", "reason": "An empty test file also passes; add a check that the file has at least one test per rule"}
    ],
    "overall": "Expectations check presence more than correctness."
  }
}
```

| Field | Meaning |
|---|---|
| `expectations[]` | Each expectation with `text`, `passed` (true or false) and `evidence` |
| `summary` | Counts and `pass_rate`, from 0.0 to 1.0 |
| `claims[]` | Claims found in the output, each `factual`, `process` or `quality`, with `verified` and `evidence` |
| `eval_feedback` | Optional suggestions to improve the evals; present only when the grader found a real gap |
