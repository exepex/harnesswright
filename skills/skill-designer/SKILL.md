---
name: skill-designer
description: Design, source, evaluate and improve harnesswright skills (SKILL.md folders) to the harness quality checklist and portability rules. Use when asked to create a new skill, adopt or adapt a skill from another repository, improve a skill's steps or its description, write or run a skill's trigger and task evals, or prepare a skill to run on Claude Code, Codex or another host. Do not use to write standards rules, role files, contracts or application code, and do not use to judge a finished skill; a separate judge does that.
license: Apache-2.0. LICENSE.txt has the full terms.
metadata:
  source: anthropics/skills@ca45fc496a3436251f191354091d557da31c15b5 skills/skill-creator
  source-licence: Apache-2.0
  sourcing: adapted
---

# Skill designer

Adapted from Anthropic's skill-creator (`anthropics/skills@ca45fc4`, `skills/skill-creator`, Apache-2.0,
Copyright 2026 Anthropic, PBC). harnesswright changed it: the harness quality checklist, borrow-first sourcing,
rule IDs and contracts, the `HW-PORT` portability rules, host-neutral eval runs and a hand-off to an independent
judge. The list of changes is in `THIRD_PARTY.md` at the repository root.

## Purpose and limits

This skill makes one skill production grade, from request to hand-off. It covers the whole loop: decide what the
skill does, look for an existing skill to borrow, draft it, write its evals, run them, improve it, and hand it to a
judge.

It does not:

- write standards rules, roles or contracts (those follow [03 · Standards](../../docs/design/03-standards.md) and
  [06 · Contracts](../../docs/design/06-contracts.md));
- judge its own work. A separate judge decides whether the skill is released;
- run borrowed scripts before they are reviewed, or copy text a licence does not allow.

The authority for every rule used here is [10 · Skills](../../docs/design/10-skills.md) and `AGENTS.md`. When this
skill and those documents disagree, the documents win; report the conflict to the owner.

## Inputs

| Input | Required | If missing |
|---|---|---|
| Skill request: what the skill should do and for which role | Yes | Ask the owner one clear question. Do not guess the purpose. |
| Name of an existing skill to improve | Only when improving | Treat the request as a new skill. |
| Candidate sources to borrow from | No | Search for them in step 2. |
| Hosts to run on | No | Every host that has an adapter under `adapters/`. |

When the conversation already holds a workflow the owner wants captured ("turn this into a skill"), take the
answers from it first: the steps, the tools used, the corrections the owner made, the input and output formats.
Ask only for what is still missing.

## Steps

Follow the steps in order. Each step ends with a check; do not start the next step until the check passes.

### 1. Write the purpose, limits and triggers

Write down, in a few lines each:

1. What the skill does, and what it does not do.
2. Which role uses it ([04 · Roles](../../docs/design/04-roles.md)).
3. When it must trigger: the phrases, file types and situations a real request would contain.
4. When it must not trigger: nearby requests that share words with it but need something else.
5. Its output, and which contract from [06 · Contracts](../../docs/design/06-contracts.md) that output fills.
6. The rules it applies, by rule ID.

Check: each of the six points has an answer, or a recorded question for the owner.

### 2. Search for an existing skill and choose a path

Search skills published by Anthropic, OpenAI, Google, Microsoft and GitHub, security firms such as Trail of Bits,
and community libraries. For each promising candidate:

1. Clone its repository into a scratch directory outside this repository and record the exact commit.
2. Read every file you might copy from, in full. Do not run any of its scripts or hooks yet.
3. Record its licence. The licence table in [08 · Governance](../../docs/design/08-governance.md) decides what you
   may copy. Without a licence, copy nothing.
4. Score it against the quality checklist in [references/quality-checklist.md](references/quality-checklist.md).

Then choose one path, as defined in [10 · Skills](../../docs/design/10-skills.md): **adopt** (it already meets the
checklist), **adapt** (good, but with gaps, host-specific parts or a different voice) or **write new** (nothing
good exists).

Check: the chosen path, every candidate considered, its commit and licence, and the reason for the choice are
written down. They go into the claims in step 7.

### 3. Draft the skill

Create `skills/<name>/SKILL.md`, where `<name>` uses lowercase letters, digits and single hyphens, at most 64
characters, and matches the folder name.

Frontmatter uses only `name`, `description`, `license`, `compatibility` and `metadata`, with string values in
`metadata` (`HW-PORT-01`). For an adopted or adapted skill, `metadata` holds `source`, `source-licence` and
`sourcing`; a new skill holds `sourcing: new`. Keep the original licence notice where the licence requires it, and
mark adapted files as changed.

The `description` is how a host decides to load the skill, so it carries all "when to use" information:

- Say what the skill does and when to use it, with the concrete phrases and file types from step 1.
- Say when not to use it, naming the nearby cases.
- Stay under 1024 characters and use no angle brackets.
- Write it to be found: models tend to skip a skill whose description is vague. Name the user's intent, not how the
  skill works inside.

The body follows the quality checklist. Write it so that any model on any host can follow it:

- Number the steps and make each one checkable (`HW-PORT-07`). State output formats; never rely on a model
  guessing one.
- Use plain verbs: "run the command", "read the file", "start an independent reviewer". Never name a host's tool
  (`HW-PORT-02`).
- When a step needs a host feature, name the capability. Give a single-agent fallback for steps that need no
  independence. Steps that need independence (reviewer, judge, verifier, panel voter) run in a fresh, separate
  agent and have no in-session fallback (`HW-PORT-03`).
- Put logic that must give the same result everywhere in a script: Python 3 standard library or POSIX `sh`, no
  network calls, deterministic (`HW-PORT-04`).
- Give every step that runs a script a no-script fallback (`HW-PORT-08`). Some teams forbid scripts
  (`scripts: forbidden` in `.harness/profile.yaml`), and some hosts or people refuse them. The fallback says what to
  check by reading, marks what the script would have proven `not verified`, and tells the person first that the
  check did not run. Add a task eval with `scripts: forbidden` that checks this.
- Cite rules by ID; never repeat their text. If a rule the skill needs does not exist yet, do not invent an ID.
  List the missing rule as a proposal for the owner.
- Explain why a step matters. A model that knows the reason handles cases the text did not foresee better than one
  given a bare order.
- Keep `SKILL.md` under 500 lines. Move detail into `references/`, one level deep, and say in `SKILL.md` when to
  read each file.

Then add the skill to the skills index in `AGENTS.md`, with its path and when to use it (`HW-PORT-05`).

Check: run `wc -l` on every file you created or changed and compare with the limits in `AGENTS.md`; confirm the
`name` matches the folder; confirm the frontmatter holds only the allowed fields.

### 4. Write trigger and task evals

Write the evals in the formats of [references/eval-formats.md](references/eval-formats.md), under
`evals/skills/<name>/`.

**Trigger evals** (`triggers.json`): about 20 queries, 8 to 10 that should trigger and 8 to 10 that should not.

- Make them realistic: the kind of request a person actually types, with file paths, names, a little background,
  sometimes casual wording or typos, and a mix of lengths.
- Should-trigger queries cover different phrasings of the same intent, including cases that do not name the skill.
- Should-not-trigger queries are near misses: they share words or ideas with the skill but need something else.
  An obviously unrelated query tests nothing.
- Make each query substantial. Hosts do not consult a skill for a task they can do in one easy step, so a trivial
  query fails whatever the description says.

**Task evals** (`tasks.json`): two to five realistic tasks, each with an expected outcome and expectations.

- Each expectation is objectively checkable and has a name that says what it checks.
- Prefer expectations a script can check. Write the check once and reuse it every run.
- An expectation must be hard to satisfy without doing the work. "A file named `report.md` exists" passes for an
  empty file; check the content.
- Subjective qualities, such as tone, go to the judge and the owner, not to forced expectations.

Check: the files match the formats; every task has at least one expectation; the trigger set has both kinds of
query.

### 5. Run the evals on the reference host and improve the skill

Claude Code is the reference host ([10 · Skills](../../docs/design/10-skills.md)). Use the eval runner,
`evals/runner/run_evals.py`, with that host's adapter under `adapters/<host>/`; its `README.md` lists the commands.
Run `triggers` and `tasks` (with `--baseline` too), have each task run graded, then run `score` for both. Keep the results
outside the repository until the final run. The runner gives each query and task to the host, records what
happened and writes the results; it never decides a result by guessing.

If no runner or adapter exists for the host, run each task eval by hand:

1. Start a fresh agent on the host with the skill installed. Give it only the task prompt and the input files.
2. Save everything it produces, and its transcript, to a scratch directory outside the repository, one folder per
   task and run.
3. Run each task at least 3 times, and as often without the skill (for a new skill) or with the previous version
   (for an improvement). This baseline shows what the skill adds; fewer runs cannot decide a label.

If the host cannot start a fresh agent, run the tasks one at a time in your own session and mark those results
`in-session`. They help you improve the skill, but they do not count toward release. Trigger evals cannot be run
by hand reliably; mark them `not run` until a runner exists for the host.

Grade each run in a fresh agent that follows [references/grader.md](references/grader.md). Script checks run
first; the grader judges the rest and critiques the evals. Grading needs independence from you, so it has no
in-session fallback.

Then improve the skill:

1. **Generalise from the failures.** The skill will run on many requests, not on these few. Prefer a clearer
   explanation or a different approach over a narrow patch that only fixes one eval.
2. **Keep it lean.** Read the transcripts, not just the outputs. Remove text that makes the agent waste effort.
3. **Explain the why.** If you find yourself writing a rule in capitals, write the reason instead.
4. **Bundle repeated work.** If several runs wrote the same helper, write it once in `scripts/` and tell the skill
   to use it.

To tune the description, give the trigger results to yourself as data: run `triggers` with `--holdout 0.4`, so
about 60% of the queries train and the rest are held out, improve the description on the training failures only,
test each new version with `--description`, and keep the version with the best held-out score. Do not list eval queries in the description; describe the intent behind them.

To compare two versions of a skill, use a blind comparison in a fresh agent that follows
[references/comparator.md](references/comparator.md).

Repeat runs into a new iteration folder until the task evals pass, the trigger accuracy meets the threshold, or
you stop making progress. If you stop making progress after three iterations, stop and ask the owner one clear
question.

Check: on the reference host, task pass rate and trigger accuracy meet the thresholds in
[10 · Skills](../../docs/design/10-skills.md) (by default at least 90% each).

### 6. Run the evals on every supported host

Run the same evals, with the same inputs, on every host that has an adapter. Compare each host with the reference
host against the thresholds in [10 · Skills](../../docs/design/10-skills.md): task pass rate at least 90%, at most
10 percentage points below the reference host, and trigger accuracy at least 90%.

When a host fails, fix the skill, never the eval, and keep the fix host-neutral. Anything that only one host needs
belongs in that host's adapter. After a fix, rerun every host, because a fix for one can break another.

If a host cannot run here (no command-line tool or no credentials), record it as not run with exactly what is
missing. Never estimate, simulate or copy a result from another host.

Write the labels with the runner's `label` command to `evals/results/<name>.json`: `verified` (run and within the
thresholds), `unsupported` (run and short of them, with the gap) or `compatible` (reads the standard, not run).

Check: `evals/results/<name>.json` holds a label for every host and model pairing, each with its gaps or reason.

### 7. Record provenance and hand off to a judge

1. Make sure the skill's `metadata` and `THIRD_PARTY.md` record the source repository, commit, path, licence and
   path taken. Add the source to `THIRD_PARTY.md` if it is new.
2. Write claims in the claims contract ([06 · Contracts](../../docs/design/06-contracts.md)): the request, quoted;
   each checklist item with its evidence; the rules applied by ID; the eval results per host; what is out of scope;
   every file changed with its line count; and what you could not verify.
3. Start a fresh, separate agent as the judge. Give it only the skill folder, its evals, the eval results and the
   claims; never your reasoning or this conversation. It checks each claim and writes a verdict in the verdict
   contract.
4. If the host cannot start a separate agent, stop and ask the owner. Never judge the skill yourself.

Check: a verdict exists for the exact commit judged. A `fail` sends you back to the step it names.

## Failure handling

| Situation | What to do |
|---|---|
| The request is unclear about purpose or output | Ask the owner one clear question before drafting. |
| A candidate source has no licence | Learn from the idea only; write your own text. |
| A borrowed script must run to be evaluated | Read it in full first, and record that you reviewed it. |
| A step's check fails | Fix it and redo the check. Do not continue with a failed check. |
| Evals keep failing after three iterations | Stop and ask one clear question, with the results and your options. |
| A host fails only because of a host feature | Move the host-specific part to `adapters/<host>/`; keep the skill neutral. |
| A host cannot run | Record `not run` and what is missing; tell the owner. |
| A file goes over its line limit | Split it by purpose; never join lines to squeeze it. |

## Output

- The skill folder `skills/<name>/`.
- Its evals in `evals/skills/<name>/`, and the results per host.
- An updated skills index in `AGENTS.md`, and `THIRD_PARTY.md` when a source was used.
- Claims for the judge, and the judge's verdict.

## Examples

**Description.**

Good: "Write unit tests for one function or class, named after the scenario and the expected outcome. Use when
asked to add, fix or extend unit tests, or when a story lists unit tests as expected. Do not use for integration,
API or performance tests."

Bad: "Helps with tests." It says neither when to use it nor when not to, so a host cannot choose it reliably.

**Step.**

Good: "Run the test suite with the command in the profile's `toolchain.test`. Check: the command exits with 0 and
every new test is listed in its output."

Bad: "Make sure the tests are fine." It cannot be checked, and different models will read it differently.

**Host neutrality.**

Good: "Start an independent reviewer that receives only the story and the change."

Bad: a step that names one host's sub-agent tool. Another host has no such tool, so the step fails there.

## Reference files

- [references/quality-checklist.md](references/quality-checklist.md): the twelve checklist items and the evidence
  each one needs. Read it in steps 2 and 7.
- [references/eval-formats.md](references/eval-formats.md): the formats of trigger evals, task evals and grading.
  Read it in step 4.
- [references/grader.md](references/grader.md): instructions for the independent grader. Give it to the grading
  agent in step 5.
- [references/comparator.md](references/comparator.md): instructions for a blind comparison of two versions. Give
  it to the comparing agent when you need one.
