---
name: skill-designer
description: Make or change a harnesswright skill in stages, one stage per run, each ending with a stage report that names who does the next step. It writes a skill's trigger and task cases first, then its template once goldens and a baseline round exist, then lists it once a round verifies it, and it decides whether a borrowed skill is adopted, adapted or written new from its licence. Use when asked to create a skill, adopt or adapt one from elsewhere, improve a skill's description or steps, fix a skill that failed its round, write its evals, or make it run on every host. Do not use to write rules, role files, contracts, scripts outside a skill, CI workflows or application code, to use a skill for its own job, to explain the docs, or to judge or review a skill.
license: Apache-2.0. LICENSE.txt has the full terms.
metadata:
  roles: skill designer
  areas: rest
  source: anthropics/skills@ca45fc496a3436251f191354091d557da31c15b5 skills/skill-creator
  source-licence: Apache-2.0
  sourcing: adapted
---

# Skill designer

Adapted from Anthropic's skill-creator (`anthropics/skills@ca45fc4`, `skills/skill-creator`, Apache-2.0, Copyright
2026 Anthropic, PBC). harnesswright changed it: the work runs in stages, evals come before the skill, rules are cited
by tag, and goldens, rounds and judging are left to others. The list of changes is in `THIRD_PARTY.md` at the root of
the harnesswright repository.

## Purpose and limits

This skill works in stages, because the goldens and rounds that a skill's evals need are made by other agents.
Each run finds its stage from what exists, does only that stage, writes only the files that stage allows,
and ends with a stage report.

Needs: the rules index the project names, such as `v2/rules/core/index.md`; for stage 2 and 3, the round's label
file; for an improvement, the round report.

Rules: {{rule:CORE-SKILL-01}}, {{rule:CORE-SKILL-24}}, {{rule:CORE-SKILL-25}}

| Stage | Starts when | Does | Next step, and its owner |
|---|---|---|---|
| 1 Evals | A request, and no cases for the skill | Source and path; trigger and task cases | Goldens by an author who did not write the cases; kit approval by the judges; a baseline round without the skill by the eval owner |
| 2 Draft | Cases, and a round's label file for the skill that meets the stage 2 test of step 2 | A new skill: template, licence, provenance, job row. An improvement: only the change its failed cases call for. Then the version and the release build | A round by the eval owner: the skill and no skill; for an improvement, the changed skill, its previous version and no skill |
| 3 Ship | A round's label file says `verified` on the reference host | Checks the release is the one the round measured; lists the skill | Claims by the role whose job they are, then an independent judge |

Files each stage may write, besides the run folder and its own report `evals/skills/<name>/stage-<n>.md`:

- stage 1: only files under `evals/skills/<name>/`;
- stage 2: `v2/skills/<name>/`, `v2/VERSION` and `release/`, and for a new skill also `v2/roles.md` and
  `THIRD_PARTY.md`;
- stage 3: only `AGENTS.md`.

This skill does not:

- write or settle goldens, approve the measuring kit, pick a fault seed, run a round or report a round's result;
- judge or review a skill, its own or another. A request to judge goes to the skill judge role;
- write rules, role files, contracts, scripts outside a skill, CI workflows or application code.

## Inputs

| Input | Required | If missing |
|---|---|---|
| The request: the skill's job, what it produces, and the role whose work it is; or the skill to change | Yes | Stop. Where the project's rules allow one, put one question in the report that covers what is missing: "What should the skill produce, and for which role?" Never choose either yourself. |
| The round's label file (stage 2 and 3), at the path the request names, such as `<store>/<round>/labels/<attempt>.json` or a file under `evals/results/` | For stage 2 and 3 | Stop. Where the rules allow one, put this question in the report: "Which label file should I read?" |
| The round report that lists the failed cases, for an improvement | For an improvement | Stop. Where the rules allow one, ask for it in the report; a label file holds counts only. |
| A source to borrow from: a folder or a repository, with its commit and licence | No | Without one, search the published skill collections the request or project names. With no source, write new. |
| The rules index the project names, for the rule IDs | Yes | Stop: a skill cannot cite rules it cannot read. |

Rules: {{rule:CORE-SKILL-28}}, {{rule:CORE-WORK-07}}

`<name>` is the skill's name: lowercase words joined by `-`. The run folder is
`.harness/runs/<YYYY-MM-DD>-skill-<name>/`. Read every file of a borrowed source in full before you copy from it,
and never run a borrowed script before a person has reviewed it.

## Steps

Do the steps in order. Each ends with a check; do not start the next until it passes. After any stop, still do
steps 6 and 7.

### 1. Check what the run needs, and read its rules

1. Check the request and each item under Needs; check the label file and the round report only when
   `evals/skills/<name>/cases/` exists. On a missing one, do as Inputs says, and write nothing else.
2. If `rules.md` or `rules-text-skill-designer.<stack>.md` is missing from the run folder, run the standards
   reader's command from the project root. `SKILL_DIR` is the folder that holds this `SKILL.md`.

   ```sh
   python3 SKILL_DIR/scripts/resolve.py --repo . --run <YYYY-MM-DD>-skill-<name> --date <YYYY-MM-DD>
   ```

   - Exit 0: go on.
   - It could not run (scripts forbidden in `.harness/profile.yaml`, no Python, or
     `.harness/profile.yaml: is missing or cannot be read`): write the files by reading, as below.
   - Any other result: stop, and report the command's output.
3. By reading, write only the missing files, and keep a `rules.md` that exists. A new `rules.md` holds the run ID,
   the date and the line `not verified: <the reason>`. Write one rules text for each language the profile names, or
   one named `core` when there is none, holding the rules you can read from the `rules/core/` and
   `rules/<language>/` folders of the release the profile names and the layer folders it lists, and `None.` when
   there are none (always, when there is no profile). Start each with the heading
   `### Changes to rules that reach this run` and one line for each rule a layer replaces, waives or tightens, as
   `- <ID> · <title>: replaced by <ID>`, `waived until <date>: <reason>` or `tightened by <ID>`, or `None.`. End
   each with the quoted value of `READ_BACK` in `SKILL_DIR/scripts/copyform.py` (open the file; reading it runs
   nothing), the line `Stack: <stack>. Rules in this text: <count>. Last rule: <ID · title, or none>.`, then the
   quoted value of `READ_BACK_END`. Add the reason to Not run.
4. A skill touches no stack's code, so read every rules text in the run folder. Apply every rule in them and in the
   rules of this skill; where a rules text replaces, waives or binds one of them, it wins.

Check: nothing the run needs is missing; the run folder holds `rules.md` and the rules texts, and you read them.

### 2. Find the stage

1. Look for `evals/skills/<name>/cases/`. With no case folder there, the stage is 1, even when the request asks for
   the skill itself: say so in the report.
2. With cases, read the label file the request names. It must name this skill, for either stage; when it does not,
   treat it as missing (Inputs). Compare the rounds of a results file only by its `compared` list: only `same setup`
   compares; read a round marked `not comparable: setup changed` or `unknown` on its own, never as a regression,
   and with no `compared` list read every round alone.
   Stage 3 needs the label `verified` on the reference host. Otherwise the stage 2 test applies, and it is the only
   one: the label's no-skill arm has at least 3 scored runs of every task case, and for an improvement the round
   report lists the failed cases. When the test fails, treat the label file as missing.
3. The test reads only the label file and the round report. Goldens are kept by others and are not in the project:
   never search for them, and never stop because you see none. A project may hold only some of the cases, as
   samples; that is no reason to stop either.

Check: you know the stage and why, from files you read.

### 3. Stage 1: write the evals

1. Settle what the skill is for, what it does not do, its inputs and the role whose job it does. They decide the
   cases; the template that states them comes in stage 2.
   Rules: {{rule:CORE-SKILL-28}}
2. Choose the path, one of three, each with its source repository, commit, path and licence:
   - **adopt**: the source meets the rules as it is and its licence allows copying;
   - **adapt**: the licence allows copying, and the text needs changes;
   - **write new**: nothing is worth borrowing, or the source has no licence or one that forbids copying. Then copy
     no sentence of it.
3. Write the trigger cases, each in a folder of its own, `evals/skills/<name>/cases/trigger-tNN/`, holding
   `case.json` and `world/`: at least eight prompts that should load the skill and eight near misses that should
   not. Write prompts as people type them. Each states `should_trigger` and `split`; half of each kind is `test`.
   Never list prompts in one shared file.
4. Write at least two task cases, each in a folder of its own holding `case.json` and `world/`. Its `expectations`
   list what a good run must show. Write each from a fact in the case's own world, cited by file and line, or
   mark it `format` when it is only the shape of the skill's own output; never from the source skill's steps or
   wording.
5. Keep the skill out of the worlds: no world holds the skill's name or its text.
6. On the write-new path with a source, compare every file you wrote with every file of the source: no eight words in a row may
   match, ignoring case and punctuation. Run the copy check from the project root:

   ```sh
   python3 SKILL_DIR/scripts/shared_runs.py --source <source folder> --written evals/skills/<name>/
   ```

   - Exit 0: no shared run. Exit 1: reword each run it prints, then run it again.
   - It could not run (scripts forbidden in `.harness/profile.yaml`, no Python, or the host or the person refused
     it): tell the person the check did not run, then compare by reading, looking hardest at expectations: each
     must rest on a world fact or be marked `format`, never on a source step. Put "copy check by reading, not verified" under Not run.
   - Exit 2: stop, and report its output.

   List the command and its result under Checked.

Check: every case is a folder with both files; the counts and the split hold; on the write-new path with a source,
the copy check passed or is under Not run; you wrote nothing outside the stage's files, and no golden or round
result.

### 4. Stage 2: write the skill

**An improvement changes only what its failed cases call for.** Change nothing else in the template, even a part
that breaks a rule: name such parts under Next as proposals. Skip 2 to 4 below unless a failed case calls for them.

1. Note the label's no-skill pass rate. For an improvement, list the failed cases from the round report and, for
   each, the part of the template that caused it.
2. For a new skill, write `v2/skills/<name>/SKILL.tmpl.md`:
   - the frontmatter, with `roles` and `areas` under `metadata`, and for a borrowed skill also its `source`
     (`<repository>@<commit> <path>`), `source-licence` and `sourcing`;
     Rules: {{rule:CORE-TEMPLATE-03}}
   - the description, in its own words, never a case prompt;
     Rules: {{rule:CORE-SKILL-03}}, {{rule:CORE-CATALOG-01}}
   - the sections: purpose and limits, inputs, steps, failure handling, output and examples;
     Rules: {{rule:CORE-SKILL-28}}, {{rule:CORE-SKILL-10}}, {{rule:CORE-TEMPLATE-06}}, {{rule:CORE-SKILL-29}}
     Rules: {{rule:CORE-SKILL-05}}, {{rule:CORE-SKILL-09}}, {{rule:CORE-SKILL-07}}, {{rule:CORE-SKILL-18}}
     Rules: {{rule:CORE-SKILL-19}}
   - the rules the skill depends on, each as a rule tag, `{{rule:<ID>}}` with the rule's ID in place of `<ID>`, on
     a `Rules:` line under the step that depends on it, or under the purpose. Tag only IDs the project's rules index
     lists. On the adapt path, remove each source sentence that a listed rule covers, and tag that rule under the
     step whose output it governs. The skill you are reading is a release file: the build wrote each of its tags
     out as "ID (title)". In a template, write neither that form nor a bare ID. A step and its line look like this,
     with real IDs in place of `<ID>`:

     `2. Write the summary of the change for the reviewer.`
     `   Rules: {{rule:<ID>}}, {{rule:<ID>}}`

     Rules: {{rule:CORE-TEMPLATE-05}}
   - any scripts the skill runs, and its bundled files, each linked with when to read it.
     Rules: {{rule:CORE-SKILL-20}}, {{rule:CORE-SKILL-21}}
     Rules: {{rule:CORE-SKILL-27}}, {{rule:CORE-SKILL-12}}
3. For an adopted or adapted source, keep its licence and copyright notice in a file in `v2/skills/<name>/`, and
   add a `THIRD_PARTY.md` section with the repository, commit, path, licence and sourcing, and what changed.
4. Add the skill's row to the Jobs table of `v2/roles.md`, with its role.
5. Raise `v2/VERSION`: the middle number for a new skill, the last for a change.
6. Build the release and check it, from the project root, with `<base>` the commit your change starts from and
   `<run>` the run folder:

   ```sh
   python3 v2/build/build.py
   git add -N . && git diff --name-only <base> > <run>/changed.txt
   python3 v2/build/check_rules.py --changed <run>/changed.txt
   git show <base>:release/manifest.json > <run>/base-manifest.json
   python3 v2/build/check_release.py --base <run>/base-manifest.json
   ```

   Report each command's exit code and the lines that matter. A command that is missing or fails is reported as it
   ran: never write that the release is built when no build passed.
7. Count the template's lines.
   Rules: {{rule:CORE-TEMPLATE-02}}

Check: you wrote nothing outside the stage's files; every rule tag in the template is on a `Rules:` line and names
an ID in the project's rules index, no bare rule ID is left, and no line this stage wrote states a rule's duty; for
an improvement, every changed line traces to a failed case.

### 5. Stage 3: list the skill

1. Run `git diff <label commit> -- v2/skills/<name>/ release/<name>/`. A change beyond the version and content-hash
   lines that a version bump makes means the skill changed after the round: go back to stage 2 and ask for a round.
   When `git` cannot run here, as with no repository, compare instead the label's `skill_sha256` and version with
   the skill's hash and version now in `release/manifest.json`, naming both values. A difference means the same;
   so does no manifest, or a value you cannot find.
2. Check that the metadata, the notice file and `THIRD_PARTY.md` agree on the source and its licence.
3. Add or update the skill's row in the skills table of `AGENTS.md`: name, path to `release/<name>/SKILL.md`, and
   when to use it.
   Rules: {{rule:CORE-SKILL-23}}

Check: the skill is unchanged since the round, provenance agrees, and you wrote nothing outside the stage's files.

### 6. Write the stage report

Write `evals/skills/<name>/stage-<n>.md` with exactly these seven second-level headings, in this order, and no
other heading. After a stop, Not run opens with the line `Blocked: <what is missing or failed>`, naming the file,
folder, tool or input exactly; with no job named, or before step 2 found the stage, give the seven sections in
your final message instead.

1. `## Stage`: the number and why, from step 2.
2. `## Request`: the request, quoted with `>` on each line.
3. `## Path`: adopt, adapt or write new, with the source's repository, commit, path and licence, and the reason.
4. `## Files written`: one line per file the run added or changed, other than this report and the run folder, as
   `` - `path` (N lines) ``, N from `wc -l` after the file is final, and no other line.
5. `## Checked`: each check and how: the command and its result, or the file you read. Give the sha256 of
   `rules.md` and quote each rules text's read-back block.
6. `## Not run`: everything you did not run or could not prove, with why. `None.` only when nothing is missing.
7. `## Next`: the next step from the stage table, with its owner; for an improvement, the failed cases by name and
   any proposals. Ask for a round; never report one.

Check: the file exists with the seven headings only, and Files written lists every file the run wrote with its
true count.

### 7. Report

After a stop, open with the same `Blocked:` line. Give the path of the stage report and its Next section. Say that
the skill is not done: the next step is someone else's, and only a round and a judge can show the skill works.

Check: your message matches the stage report.

## Failure handling

| Situation | What to do |
|---|---|
| Something the run needs is missing | Stop, with a question in the report where the rules allow one (Inputs). Write none of the stage's files: the step 6 report is the one file you still write. Then do steps 6 and 7, with their `Blocked:` line. |
| The request asks for the skill and no cases exist | Do stage 1. Say the skill comes after its goldens and a baseline round. |
| A source has no licence, or its licence forbids copying | Write new. Name the source and the missing licence in Path. |
| You find no goldens for the skill | Expected: others keep them. The label file is the evidence; do not search or stop. |
| A borrowed script exists | Do not run it. Name it under Not run, for a person to review. |
| The build or a check is missing or fails | Report the command, its exit code and its output. Do not claim the release. |
| A round cannot name a new skill that has no folder yet | Say so under Next, for the eval owner. Never write the skill early to get round it. |
| The request asks you to judge the skill or settle its goldens | Refuse that part, and name who owns it in Next. |

## Examples

**A Next section.** Good: "Goldens for both task cases, by an author who did not write these cases. Kit approval by
the judges. A baseline round without the skill on both hosts, 3 runs per case, by the eval owner." Bad: "Next: run
the evals and ship." It names no owner, and it would have the designer measure its own work.

**A Path section.** Good: "Adapt. `acme/agent-skills` at `9f3e2d1`, path `skills/lint-fixer`, MIT: the steps are
sound, the tool names are not." Bad: "Adapted from a skill the team found." It names no commit and no licence, so
nobody can check it.
