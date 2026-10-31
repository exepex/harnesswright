---
name: claims-writer
description: Write the claims file for a finished story, the evidence an implementer hands to the story judge. For each acceptance criterion it runs the command that proves it, reads the output and records what was done with file:line, test names and command output, then lists the standards applied, what is out of scope, every file changed with its line count, and what could not be verified. Use when a story or change is finished and someone asks to write the claims, prove the work is done, prepare a change for the judge, or record evidence for each acceptance criterion, in any language or build tool. Do not use to write or fix the code itself, to write a story or plan, to judge or review someone else's change, or to write a pull request description or commit message.
license: Apache-2.0. Adapted text keeps its MIT notice in LICENSE-MIT.txt.
metadata:
  source: obra/superpowers@2ce8aa15d05bd57213e6f746f953aafb7ded7a8b skills/verification-before-completion
  source-licence: MIT
  sourcing: adapted
---

# Claims writer

Adapted from `verification-before-completion` in `obra/superpowers@2ce8aa1` (MIT, Copyright 2025 Jesse
Vincent). harnesswright changed it: the output is the claims contract, the steps are numbered and checkable,
inputs and failure handling are added, and a script checks the result. The list of changes is in
`THIRD_PARTY.md` at the repository root.

## Purpose and limits

The implementer uses this skill when a story is finished. It writes the claims: a file that tells the story
judge, for each acceptance criterion, what was done and the evidence that proves it. The judge never sees the
implementer's reasoning ([04 · Roles](../../docs/design/04-roles.md)), so the claims and the change are all it
has. A claim without evidence makes the judge redo the work or reject the story.

The rule behind every step: **no claim without fresh evidence.** If you have not run the command that proves a
claim while writing these claims, you cannot claim it.

This skill does not:

- write, fix or refactor code or tests. If a criterion turns out not to be met, the claims say so; fixing it is
  separate work, after which the claims are written again;
- write stories, plans, verdicts, pull request descriptions or commit messages;
- judge the change. The story judge does that, independently.

## Inputs

| Input | Required | If missing |
|---|---|---|
| The story: its acceptance criteria, and the request when the story has `plan: none` | Yes | Look for it in the run folder, `.harness/runs/<run-id>/stories/<story id>.md`. If there is none, ask one clear question: "Which story or request does this change deliver?" Never write criteria yourself. |
| The change: the files it touched | Yes | With git, run `git diff --name-only <base>` and `git status --short`. Without git, use the files the person names; if none are named, ask which files changed. |
| The commands that prove the work: build, test, lint | No | Use the profile's `toolchain` in `.harness/profile.yaml`. If there is no profile, use the commands in the README or the build files. If none exist, record the gap under **Not verified**. |
| The resolved standards for the repository | No | Write "None resolved for this repository." under **Standards**. Never invent a rule ID. |
| Whether skill scripts may run: `scripts` in `.harness/profile.yaml` | No | `allowed`. When it is `forbidden`, never run `scripts/claims_check.py`; follow the fallback in step 5. |

All paths in the claims file, in **Done**, **Evidence**, `file:line` references and **Files changed**, are relative
to the project root: the folder that holds `.harness/`. Run every command from there.

## Steps

Do the steps in order. Each ends with a check; do not move on until it passes.

### 1. Find the story and the change

1. Read the story in full. List its acceptance criteria with their IDs (`AC-1`, `AC-2`, …). If the criteria
   have no IDs, number them in the order written and say so in the claims.
2. List the files the change touched (see Inputs).

Check: you have the full text of the story and a list of changed files.

### 2. Decide what proves each criterion

For each criterion, write down the evidence that would prove it, before you look for it. Use this table:

| Claim | Proven by | Not enough |
|---|---|---|
| Tests pass | The test command's output in this session: the count and 0 failures, exit code 0 | An earlier run, "should pass" |
| Build or compile succeeds | The build command: exit code 0 | A clean linter, logs that look fine |
| Lint is clean | The linter's output: 0 errors | A partial run |
| A bug is fixed | A test of the original symptom passes now. If the commit before the fix is at hand, the same test fails there; run it in a separate checkout, never by undoing the fix in the working tree. Otherwise record that red-to-green was not shown under **Not verified**. | The code changed, so it is assumed fixed |
| Behaviour X exists | `file:line` of the code, and a test name that exercises it, with its passing output | The code exists but nothing runs it |
| A criterion is met | Each part of the criterion matched to its evidence | The test suite passes as a whole |

Check: every criterion has a planned piece of evidence, or is marked as one you cannot prove here.

### 3. Run each command fresh and read its output

Run every command you planned, now, in full: not a subset, not a result remembered from earlier. Read the whole
output. Note the exit code, the number of tests run and the number that failed or were skipped.

A check that cannot run here (no tool installed, no network, needs a staging system) is not a failure of the
change. It is a gap: record exactly what was not run and why.

Check: for each command you have its exact text, its exit code and the lines of output that prove or disprove
the claim.

### 4. Write the claims file

Write the file to `.harness/runs/<run-id>/claims/<story id>.md`, next to the story. When there is no run folder,
create `.harness/runs/<YYYY-MM-DD>-<short-name>/claims/<story id>.md`, with `S01` as the story ID when the
request had none. Use exactly these six level-2 headings, in this order, as defined by the claims contract in
[06 · Contracts](../../docs/design/06-contracts.md). Read [references/claims-template.md](references/claims-template.md)
for the full layout.

1. `## Request`: the story, quoted with `>` on each line. Do not paraphrase it.
2. `## Requirements`: one entry per criterion, headed by its ID, with **Status** (`met`, `not met` or
   `not verified`), **Done** (what changed, with `file:line`) and **Evidence** (test names, the command and the
   lines of its output that prove it, quoted in backticks or a code block). A criterion is `met` only when its
   evidence from step 3 proves every part.
3. `## Standards`: each rule applied, by its ID, with any exception and the reason for it.
4. `## Out of scope`: what the change deliberately does not do, each with a reason. Ideas for extra work go here
   as proposals, not into the change.
5. `## Files changed`: one line per file, `` - `path` (N lines) `` or `` - `path` (deleted) ``. Produce the list
   with the script in step 5; do not count by hand.
6. `## Not verified`: everything you could not prove, each with why and what would prove it. Write `None.` only
   when every claim above has evidence.

Write plainly. Words such as "should work", "probably" or "seems to" mean the evidence is missing: either get the
evidence or move the claim to **Not verified**.

Write the claims file with your host's file-writing tool, not through a shell heredoc or `echo`. A quoting slip in
a shell command can create stray files in the project, and the claims file is the only file this skill writes.

Check: the file has the six sections in order, every criterion of the story appears under **Requirements**, and no
other file in the project was created or changed.

### 5. Count the lines and check the file

First read `scripts` in `.harness/profile.yaml`. If it is `forbidden`, skip to "Without the script" below and do
not try the script: the team has decided scripts do not run here.

Otherwise run the bundled script from the project root. `SKILL_DIR` is the folder that holds this `SKILL.md`.

```sh
# The Files changed list: name the files, or give the git ref the change started from.
python3 SKILL_DIR/scripts/claims_check.py lines path/one path/two
python3 SKILL_DIR/scripts/claims_check.py lines --base main

# The check of the finished claims file. Add --base with the same ref when you have one.
python3 SKILL_DIR/scripts/claims_check.py check [--base main] .harness/runs/<run-id>/claims/<story id>.md
```

The check confirms the six sections, the quoted request, one entry per acceptance criterion of the story with a
valid **Status**, each file's line count, that **Files changed** matches the diff (with `--base`), that every
`` `file:line` `` reference points at a line that exists, and that no hedging words remain. It cannot judge
whether your evidence is true; only fresh runs in step 3 make it true.

**Without the script.** When scripts are forbidden, or the script cannot run (no Python, or the host or the person
refuses it), the check did not happen, and the claims must say so:

1. Count each changed file's lines with the project's own tools if you can, or by reading the file, and check every
   `file:line` reference by opening the file at that line.
2. Add one entry under **Not verified**: "`claims_check.py` not run: <scripts are forbidden by the profile | the
   reason it could not run>. Line counts, `file:line` references and the section structure were checked by
   reading only; the team must check them by hand." Replace a `None.` that was there.
3. In step 6, say this first.

Never write that the check passed when it did not run.

Check: `claims_check.py check` prints `claims check: ok` and exits with 0, or, without the script, **Not
verified** has the entry above.

### 6. Report

Tell the person where the claims file is, and give one line per criterion with its status. If the claims check
did not run, say first that it did not run, why, and that the team must check line counts and references by hand.
If any criterion is `not met` or `not verified`, say so next. Do not call the story done unless every criterion is
`met`.

Check: your report matches the statuses in the file.

## Failure handling

| Situation | What to do |
|---|---|
| A test or build fails | Record the failing command and its output under the criterion, set **Status** to `not met`, and report it. Do not change code to make it pass inside this skill. |
| A command cannot run here | Record it under **Not verified** with what is missing, for example "`go test ./...` not run: no Go toolchain". Never write that it passes. |
| The story has no testable criteria | Write the claims against the request, and say under **Not verified** that the criteria were not testable. |
| The claims check fails | Fix the claims file, not the check, and run it again. |
| The claims check cannot run, or the profile forbids scripts | Follow "Without the script" in step 5. Never claim the check passed. |
| You cannot tell which story the change delivers | Ask one clear question; do not guess. |

## Standards applied

No core standards exist yet. This skill applies the duties every role has in
[04 · Roles](../../docs/design/04-roles.md): report only what you verified, done means proven, do only what was
asked. Proposal for the owner: a `CORE-PLAN` rule stating that every acceptance criterion is claimed with
evidence, so this skill can cite it by ID.

## Examples

**A requirement entry.**

Good:

```markdown
### AC-2 · A negative quantity is rejected
- **Status:** met
- **Done:** `quantity` is validated before pricing, `src/orders/pricing.py:18-21`.
- **Evidence:** `test_negative_quantity_is_rejected` in `tests/test_pricing.py:40`.
  `python3 -m unittest discover -s tests` → `Ran 9 tests in 0.004s`, `OK`, exit code 0.
```

Bad:

```markdown
### AC-2
Validation added, tests should pass.
```

It names no file or line, no test and no output, and "should pass" shows the tests were not run.

**A gap.**

Good: "`go test ./...` not run: the Go toolchain is not installed here. Running it in CI would prove AC-1 and
AC-3." Bad: leaving the criterion as `met` because the code looks right.

## Reference files

- [references/claims-template.md](references/claims-template.md): the full layout of a claims file. Read it in
  step 4.
- `scripts/claims_check.py`: line counts and the structure check. Run it in step 5, unless scripts are forbidden.
