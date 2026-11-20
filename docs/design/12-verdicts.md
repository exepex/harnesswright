# 12 · Verdicts: what a round may claim

[11 · Evals](11-evals.md) says how a round runs. This document says what a round may conclude from its runs, so
that the same skill on the same setup gets the same verdict, and a pipeline can trust it.

## The one rule

**A verdict rests only on what was measured, on one setup, with the skill's use proven and its output checked.**

Each section below applies this rule to one place. Nothing in it is a fix for one case: it holds for every skill,
case and host.

## Skill kinds

harnesswright ships one thing to teams: a zip of the generated release, skills and scripts, that anyone can unpack
and use. Some skills are made for teams; others only build harnesswright itself. They are used differently, so
they are measured differently.

| Kind | Who uses it | World | Scored by |
|---|---|---|---|
| `team` | Teams, in their own repositories, from the zip | A standard team repository, with the skill installed from the release as a team would | Lift over a plain agent, on top of the floors |
| `internal` | harnesswright's own agents, such as the skill designer | A copy of the harnesswright layout at a pinned commit, without the skill under test | Reliability: the floors, and the output passing harnesswright's own checks |

- Each skill's kind is declared in `evals/kinds.json`, a part of the measuring kit, so the judges approve it and a
  round plan cannot pick the easier score. One reader gives the kind; nothing else decides it.
- A skill with no kind declared is `incomplete`.

### Team worlds

- The world is a team repository: its code, its tests, its `.harness/` folder (profile and stories, which the
  skills read) and its own notes. The notes hold the team's rules, never harnesswright's rules
  ([07 · Repository profile](07-repo-profile.md)).
- Arms, file by file:
  - **with skill:** the team repository, plus the skill's folder and the run-time files it declares (such as the
    rules and roles it reads), taken from the release;
  - **previous version:** the same set, taken from the previous release;
  - **without skill:** the team repository only.
- One reader proves the installed files equal the release's entries for that skill.
- Lift is what the skill, with the files it needs to run, adds over a plain agent in the same repository.
- Contract expectations cite the outcome a team expects, such as a story's outcomes and its tests, never the
  skill's own wording, so a plain agent can meet them.

### Internal worlds

- The world is built by one reader from an allow list of harnesswright paths at a commit pinned in the kit. The
  commit changes only with the judges' approval, so case expectations that cite a file and line do not drift.
- The skill under test is left out by one rule: every allow-listed file in which the world lint finds the skill is
  dropped or rewritten, never hand-picked. `evals/` is left out too.
- The world's `release/` is rebuilt by the build script from the world's own sources, so its manifest and the
  release check agree with what the world holds. World lint checks that the untouched world passes the build
  checks.
- A case adds or removes files on top of that world.
- Arms: with skill and previous version only. There is no without-skill arm, so there is no lift and no baseline
  backstop. A round of internal skills names a fault case of a team skill for the fault gate.
- Every internal task case has a script check, counted as a contract expectation, that runs harnesswright's own
  checks on the output, such as the release check, the rule check and the case's own tests.

### Stop and prerequisites

Every skill stops the same way, and every round checks that it did.

- **Stop.** A stopped run ends as blocked, names exactly what is missing, writes none of the work the missing
  input was for, and still runs its closing steps, such as its report. A by-reading fallback the skill offers is
  not a stop.
- **Prerequisites.** A skill names at its top the files, folders and tools it needs, and its first step checks
  them. A missing one is a stop.
- **Cases.** Each skill has a missing-prerequisite case, where a clean stop is the pass. Every task case has a
  script check: after a failed check, the run ended blocked and wrote its closing report. The `missing-input`
  pass line is a script check too: blocked, names the missing input, writes nothing; a check that the run asked
  one question is added only where the world's rules allow a question.

### Hand-offs

A skill that hands its output to another role is also tested at the hand-off: the next role's skill is given the
output and must accept it. These tests are written when the first multi-agent pipeline skill exists.

## Proven use

A pipeline loads a skill on purpose. A round does the same, and proves it.

- **Pinned load.** In task runs of the with-skill and previous-version arms, the runner starts the prompt with one
  fixed lead line from the adapter, such as "Load the skill NAME at PATH before anything else." The skill text is
  never pasted into the prompt. A host with its own way to invoke a skill may use it only if it reports a load
  event that the load proof accepts.
- The lead line is the one declared difference between the arms' prompts. It is hashed into the run key, never
  written in `case.json`, and hidden from graders by the view, so a grader still cannot tell the arm. A planted
  grader fault, a page that shows the lead line, proves the view hides it.
- **Load proof.** One reader decides whether a pinned run loaded the skill. A load is proven by an observed event,
  never by an inferred one:
  - the host's own skill event for that skill;
  - an observed read of the exact `SKILL.md` path of either installed copy;
  - an observed command whose own path argument is that `SKILL.md`, and whose output holds the whole file.
  A search over the release folder that merely mentions the skill proves nothing. A sub-agent's read counts when
  the host reports it as observed.
- **Not loaded.** A pinned run with no proven load is `not loaded`. It is tried once more. Still not loaded, the run
  is unscored, never a skill failure and never a pass, and the label is at most `inconclusive`, naming it. A case
  with no loaded run is named the same way. `not loaded` is not a void: voids stay harness faults.
- If half or more of a round's pinned tries are not loaded, each try counted as the pinned-load rate counts it, the
  round stops as a harness fault: the pin is broken, not the skill. A pinned-load probe checks the pin before any real run.
- The label gives the pinned-load rate per arm.
- **Trigger runs are not pinned.** Whether a host picks the skill by itself is measured by the trigger cases and
  reported as its own label line: the trigger label. A task verdict never reads it. In a trigger run an inferred
  load still counts, as [11 · Evals](11-evals.md) says, since some hosts report no load of their own; the label
  names how many trigger runs rest on an inferred load only.
- To list a skill as shipped, both are needed on the reference host: its task label `verified` and its trigger
  label met. The label file decides it from those two labels, and the results file copies it.

## One setup

A comparison is valid only between arms measured on one setup.

- **Setup fingerprint.** Each round records one fingerprint of everything that measures the skill: the kit, cases,
  worlds, the other skills its own cases install, the tools its cases declare as each host found them, adapters,
  host versions, each host's model, the grader routes and the label rule. It leaves out the skill's own hash.
- **Results record the skill.** `rounds.py results` writes the skill's hash and the fingerprint into
  `evals/results/<skill>.json`. It is the one place that compares rounds. Two results compare only when their
  fingerprints match; otherwise every report says "not comparable: setup changed" and names what changed.
- **Skill changed, setup changed.** The plan names the last verified version as `previous`, read from the results
  file's recorded hash, and the comparison happens inside the round.
- **Skill unchanged, setup changed.** There is no previous-version arm, since it would equal the skill under test.
  The round's verdict stands on its own, and no cross-round claim is made.

## Verdicts

A verdict is `pass`, `fail` or `too close`.

- **Split case.** A case whose runs in one arm disagree.
- **Deciding a measure.** A measure (pass rate, format conformance, lift, false-done rate, the gap to the previous
  version) is computed from per-case rates, each case's rate being its passed runs over its scored runs. It
  **fails** when it fails even at its best; it **passes** when it passes even at its worst; anything else is `too
  close`. Its best flips one failed run of each split case to passed; its worst flips one passed run of each split
  case to failed. Format conformance weights each case by its format items per run.
- Only one run per split case is flipped, so each extra run narrows the swing: a split case of 3 runs moves its
  rate by a third, one of 9 runs by a ninth. Unsplit cases are never flipped, so a clean round is decided at once.
- Pooled rates are the mean of per-case rates, so extra runs on some cases do not weigh them more.
- For a measure that reads two arms, such as lift, the gap to the previous version or the gap to the reference
  host, "best" for the skill makes the with-skill arm's flip toward pass and the other arm's toward fail; "worst"
  does the opposite. For the reference host, the other arm is the reference host's with-skill arm. Its split
  cases get extra runs on the reference host.
- Format conformance flips the items of one run, not whole runs.
- **Situation floors.** Every with-skill run of a situation case must pass. One failed run makes that situation
  `too close`; a second failure, extras included, makes it fail. `verified` still needs every floor run, extras
  included, to pass (owner decision, 2026-11-20).
- **Extra runs.** The plan names `extra_runs` (0, 3 or 6) up front, and the manifest records it; it caps the extra
  runs per split case and arm, and 0 turns them off. When a measure or
  floor is `too close`, the round adds 3 runs, in each arm the measure reads, to each split case, at most twice, and
  decides again by the same rule. The fault gate's planted runs are never extended.
- Deciding again gives a borderline skill at most two more chances. This is accepted: the bar for `pass` does not
  move.
- A `too close` measure after the last extra runs gives the label `too close`, which never counts as `verified`.
- A run's grade is made once and kept across attempts, with the golden result its graders were trusted under. Each
  attempt's golden gate still covers it; a grade whose graders lose trust is unscored. Extra runs are graded with
  goldens mixed in, like any run.

## Grader agreement

- Agreement is counted for each judged question across the round, including answers refused for their form and
  asked again.
- A page's answer is settled when the graders and the tie-breaker give a majority and no retry flipped it. A run is
  unscored on a question only when that page's own answer is not settled, for a pass and a fail alike.
- The label names every question below 90% agreement and every question whose retry flipped. Those questions are
  rewritten as a script check, sharpened, or dropped, and their goldens settled again by a judge who did not write
  them. Low agreement unscores nothing by itself.

## Why an attempt ended

Every way an attempt ends, a gate stop, a time limit or a crash, writes its reason to the attempt record before
the process exits. A resumed round prints the last reason, and the round report names every attempt with no
recorded reason.

## Labels by kind

The labels and thresholds of [10 · Skills](10-skills.md) apply (pass rate, format conformance and trigger
accuracy at 90%, and the floors), read this way. The label rule, its thresholds and its code, is a part of the
measuring kit in `evals/kit.json`, so the judges approve any change to it.

| Label | Team skill | Internal skill |
|---|---|---|
| `verified` | Every measure and floor passes, lift above zero, not worse than the previous version | Every measure and floor passes, not worse than the previous version |
| `too close` | A measure or floor is still too close after the extra runs | The same |
| `unsupported` | A measure or floor fails, other than lift | The same |
| `inconclusive` | Unscored runs, not-loaded runs, too few runs, or lift that fails (as today, no lift is not a failure of the skill); a lift still too close after the extra runs gives `too close` | Unscored runs, not-loaded runs or too few runs |
| `incomplete` | A result is missing, or no kind is declared | The same |

An internal skill is at most `inconclusive`, with each such case named, while any of its task cases has no
contract expectation decided by a script check that `evals/own-checks.json`, a kit part, lists as harnesswright's own.

## Build order

This design is built in small parts, in this order: load proof, pinned load, one setup, the label split, kinds and
verdicts, extra runs, grader agreement, attempt reasons, the stop standards in the skills, worlds by kind, and the
rewrite of judged questions. Until a part is built, [11 · Evals](11-evals.md) describes what runs.
