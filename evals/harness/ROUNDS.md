# Eval rounds

The rounds of the eval harness ([README](README.md)): one plan, one manifest, and every gate in order.

A round starts from a plan file: the round's name, the skills with the cases to run, the hosts (each adapter once,
with the model it runs, always named, as not every host reports its model and a default changes) and the runs per
case, arm and host. `rounds.read_plan` checks it against one schema, `rounds.PLAN`, and refuses any other field or
shape. `python3 evals/harness/rounds.py plan PLAN.json --store DIR` writes the round's manifest to
`DIR/<round>/manifest.json`, outside the working tree: the plan and its hash, the commit, the kit's hash, the hash
of every skill an arm installs (the skills under test and every sibling) with its upstream source and the hash of
its stored copy (`evals/skills/NAME/upstream/`), each case's hash (its `case.json` and world), each adapter's
tracked files, and each host's program, hash and version as the host's own jail finds it. A round is planned from a
clean tree, so its commit holds every input it hashes. A round's manifest is written once: the same manifest again
is kept, and any other is refused, so a changed input is a new round.

A plan may also name, under `previous`, the full commit of a skill's previous version. Its task cases then run in
a third arm, `previous_version` (`runs.arms`), which installs the skill as that commit holds it, the folder
`skills.folders` reads there. `rounds.previous` is the one reader of it: it checks the commit out in a scratch
worktree with no hooks, removed afterwards, reads the skill as the version under test is read, and hashes its
tracked files. The lint gate lints that arm with the previous version's text too, and a plan whose previous
version names a skill it runs no task case of is refused. The manifest records the commit, the path and
the hash, and every run of that arm reads the skill again and must find the same hash. A previous version equal to
the one under test is refused. Trigger cases run in two arms only, as they measure the description under test.

The manifest records, under `verified`, each held skill's last version `evals/results/<skill>.json` records as
`verified` on the reference host (`results.verified`). A skill whose hash changed since then, and that the plan runs
a task case of, must name that version as `previous`, so the comparison is made inside the round on one setup (doc
12, One setup); the plan is refused otherwise, naming the round and hash. An unchanged skill, or one the plan runs in
trigger cases only (which compare no versions), needs no previous arm, and its round makes no cross-round claim. A
results entry written before skill hashes were recorded gives no hash: the manifest says it is unknown, and the plan
asks for nothing.

The manifest records each planned skill's kind under `kinds`, as `evals/kinds.json` declares it (`cases.kinds`, doc
12, Skill kinds): `team` or `internal`, or null when undeclared. The file is a kit part, so the judges approve it,
and a plan cannot set a kind. An internal skill runs with the skill and its previous version only, never without
itself (`runs.arms`, `runs.key`), so it has no lift and no baseline backstop; it cannot be absent, and its cases are
never the fault gate's. A round whose skills are all internal names a team skill's case as its `fault_case`. The
kit part `evals/own-checks.json` lists harnesswright's own checks (`cases.own_checks`, none yet), and the manifest
records the list: an internal skill's label is at most `inconclusive` while one of its task cases has no contract
expectation that one of them checks, each such case named (`verdicts.decide`).

A new skill's first baseline round needs no skill folder. A skill the plan names that has cases but no folder yet is
`absent` in the manifest: an empty overlay. Its task cases run in the without-skill arm only (`runs.arms`), which
the lint gate lints; a trigger case or a previous version for it is refused. Every fault needs a skill's files, so
the fault gate plants on a case of a skill the repository holds: the plan's `fault_case`, which the manifest hashes
and installs, or else one of the round's own cases of a held skill. A plan whose skills are all absent must name a
`fault_case`.

Each run of a round is one case, in one arm, on one host, with its number. `runs.key` names it by the hash of
everything that decides it: the case, every skill an arm installs, the adapter, the host's version and model from
the manifest, the arm, the number, the run's own settings (the drift record, which decides what evidence counts as
the agent's, and the time budget, since a run that timed out is scored), and the runner code that affects a run
(`runs.RUNNER`: the jail, the gate, the host contract, the world builder, the evidence and `runs.py` itself). The
jail's settings are not in the key: the jail is audited on every run, and one that fails its audit stops the round.
`runs.run` makes a run only from the repository at the round's commit, clean, so it builds exactly the inputs the
manifest hashed. It keeps a run whose folder, `<store>/<round>/runs/<key>/`, holds a bundle that loads, so a resumed
round remakes only missing or voided runs. Otherwise it builds and proves both arms, runs the chosen arm in its
jail, collects its evidence and stores the bundle, written beside its name and moved into place. A run is void, with
`void.json` listing why, only for a harness fault: the host failed, its version is not the manifest's, or a
without-skill run holds one unbroken span of at least 16 words of the skill's own text in one of its texts (the
baseline backstop, `backstop.py`). A backstop void keeps its bundle under `voids/<n>/bundle` for a judge to read,
never scored; a shorter match is listed in `backstop.json` beside the bundle and in the run gate's report. What the
agent did, a run that timed out included, is scored, never voided. A voided slot gets one remake; voided twice, it
stays empty. `void.json` stays beside a remade bundle, so the void rate per arm can be counted. A jail that fails
its audit, or a canary in any output, raises, and the round stops. A pinned run (`runs.pinned`: a task run with the
skill or its previous version, in a round whose manifest pins the load) whose evidence proves no load
(`evidence.loaded`) is `not loaded`, never a void: its bundle goes to `not-loaded/<n>/bundle`, never scored, and
`not-loaded.json` lists why. It is tried once more at once; not loaded again, the slot stays unscored. When half or
more of the pinned tries are not loaded, counted as the pinned-load rate counts them, the run gate stops the round as
a harness fault. A pinned run's prompt starts with the adapter's lead line (`runs.lead`, through `host.lead`), which
the run key holds with the manifest's `pinned` flag; the case keeps its own prompt, which the grader page shows.
Every round planned now records `pinned: true`; a manifest without it resumes unpinned.

`python3 evals/harness/rounds.py run ROUND --store DIR` takes a planned round through its gates in order
(`gates.GATES`): the kit check, lint of every planned case on every host, the probes, the faults, the runs, the
checks and the grades. Each gate reads only the manifest and what the gates before it found, and the first that
fails stops the round with its reason. A host that fails a probe is `not run` for the round; the round stops only
when no host passed. The drift record of the first attempt a host passed is kept as the round's
(`<store>/<round>/drift/<host>.json`) and used by every later attempt, so run keys stay the same from one attempt to
the next. Tools that are not the round's stop the round. Every fault of the catalogue is planted on each host that
passed, at a place the round's seed chooses, and every one must be caught. The runs follow `gates.order`: for each
number, each case in turn, its arms one after the other, the arm that goes first turning. The host's version
is measured just before each run, so a host that changed during the round voids its runs. The check gate decides
every expectation that has a check on the bundle of each kept or made run, with the check library of the round's
commit, and writes the verdicts beside the bundle (`<store>/<round>/runs/<key>/checks.json`); what no check decided
goes on to the graders. The grade gate grades every run's and golden's page in one blind order (`grades.py`). A
run's answer counts only where the goldens got their settled answers. Each graded page leaves one record in the
attempt's own folder (`<store>/<round>/grades/<attempt>/`). A run's grade is made once and kept across attempts
(`<store>/<round>/kept-grades/<key>.json`) with the golden result its graders were trusted under; a later attempt
grades its goldens again and counts a kept answer only when its question is trusted both now and then. When a
measure or floor is `too close`, the extra runs gate (`extras.py`) adds 3 runs to each split case it reads, in each
arm it reads, through the run, check and grade steps, at most as many per case and arm as the plan's `extra_runs`
(0, 3 or 6), and decides again; the fault gate's runs are never extended, and a label already bound to be
`incomplete` or `inconclusive` by another reason gets none, the gate's outcome saying why (`skipped`). A regrade
reads the same runs as the label (`labels.with_extras`). The label file names the extra runs of
each case and arm (`extra_runs`). A check that breaks, a grader that breaks its jail or a
golden that cannot be built stops the round. Each gate's outcome, that of the gate that stopped the round too, is
written, as it ends, to the attempt record `<store>/<round>/attempts/<time>-<random>.json`, with the seed.
Everything a round writes or reports, its drift records included, passes one scrub: the canaries and credentials of
every containment its gates made, taken while its home is still there. Every gate, grading too, as goldens
calibrate only their own attempt's graders, runs again when the round runs again; only runs and their grades are
kept.

The label gate (`labels.py`, with `verdicts.py` and `triggers.py`) gives each skill on each host one label of [10 ·
Skills](../../docs/design/10-skills.md), computed from the store alone: the attempt record, and for each kept or
made run its bundle, its `checks.json` and its trusted grades. One rule holds: a label rests only on settled
results. A task run passes when every contract expectation of its case passed, a check deciding first and a trusted
`yes` deciding what no check did; it fails when one failed, and is not scored when one has no trusted answer. Format
expectations do not count, as only the skill knows its own format. A trigger run, scored in the with-skill arm only,
passes when the skill loaded exactly when the case says it should. A load the adapter inferred from a read of the
skill's `SKILL.md` counts, as the discovery probe counts it, since some hosts (Codex) report no skill load of their
own. A trigger case passes when the skill loaded in at least half its runs if it should trigger, and in fewer than
half if it should not.

The trigger cases give the trigger label, a line of its own in each host's entry (`trigger`, `triggers.label`): the
accuracy of the `test` split against its 90% threshold, how many trigger runs rested on an inferred load only, and
`met`, with each gap named (no test trigger case, too few scored runs, a trigger run not scored, or the accuracy
below its threshold). The task label never reads it, and a trigger run not scored is named there only.

The task label reads the skill's kind (doc 12, Labels by kind). A host that was not run, a skill with no kind
declared, an absent skill (its label file still gives the baseline pass rate and the scored runs per case), or a
skill with no task case is `incomplete`. Every planned run that is not scored (void, empty, not loaded or
undecided), a case and arm whose pinned runs never loaded, too few scored runs, missed goldens, a reference host
whose result is not settled, or, for a team skill only, no lift make it `inconclusive`, each named. An internal skill
has no without-skill arm, so no lift: it is scored by its floors. A skill whose round ran its previous version must
be at least as good as it on the same task cases, in pass rate and false-done rate; too few scored runs in that
arm, or no decided false-done answer in either arm, keep it `inconclusive`. The label file goes to
`<store>/<round>/labels/<attempt>.json`.

Each measure is decided `pass`, `fail` or `too close` by one rule (`verdicts.judge`, doc 12, Verdicts), and the
label file names each one under `verdicts` with its value, best and worst. Rates are the mean of per-case rates,
each case's rate its passed runs over its scored runs (`verdicts.mean`); format conformance weighs each case by its
format items per run. The label file gives what they are read from: `per_case`, each arm's passed and scored runs of
each case the rates pool, and `format_runs`, each arm's passed and asked format items of each run, by case. A split
case is one whose runs in an arm disagree: at its best one failed run of each split case passes, at its worst one
passed run fails, and unsplit cases never move, so a clean round is decided at once. A measure fails when it fails
even at its best, passes when it passes even at its worst, and is `too close` otherwise. Lift, the gap to the
previous version's pass rate and its false-done rate move the with-skill arm one way and the other arm the other.
Format conformance moves the items of one run, from each run's format items (`format_runs`). Every with-skill run of
a situation case must pass: one failed run makes that situation `too close`, a second makes it fail. A measure or
floor that fails is `unsupported`, each named, except a team skill's lift, whose failure stays `inconclusive`; one
that is `too close`, a lift included, gives the label `too close`, which is never `verified`. Extra runs are not
made yet (doc 12, Extra runs).

Where this changes a number: the task, baseline and previous pass rates, lift and the false-done comparison were
pooled counts and are now means of per-case rates, so a case with more scored runs no longer weighs more. They are
equal when every case has the same number of scored runs, as in every round so far; with 9 of 10 runs passing in one
case and 3 of 3 in another, the pass rate is 95%, not 12 of 13 (92%). Format conformance weighs each case by its
format items per run, so it equals the pooled items' share whenever each case has the same number of scored runs,
and extra runs on one case weigh it no more: two cases of 13 items failing 4 each, beside eight of 5 items passing,
score 174 of 198 (87.9%), not the plain mean's 93.85%. The label file's `false_done` and `format_conformance` per
arm, and each situation's counts, stay pooled counts.

Beside each label, `measures.py` reports what it rests on, counted from the store and never estimated, each share
with its counts: the void rate and the pinned-load rate per arm, grader agreement, golden accuracy from the goldens' grade records, the
faults the fault gate caught, how many expectations a check left undecidable on inferred evidence, format
conformance per arm with the expectations left undecided, and per arm the runs, seconds, token counts by model and
money at the price file, whose date the label file names. A run with no token counts, or a model with no price,
leaves its arm with no money, and the arm says how many runs had none. A voided try keeps no evidence, so the
cost names how many tries it leaves out.

Every task case ends with the done question (`evals/grading/done.json`), appended by `cases.Case`: does the run say
its work is done? It is graded and calibrated by goldens like any other question, and counts in no pass rate. The
label gives, per arm, the false-done rate: runs whose trusted answer is `yes` while a contract expectation failed,
of the runs where both are decided, with the runs not decided counted apart.

`python3 evals/harness/rounds.py results ROUND --store DIR --archive TAR` copies a finished round into
`evals/results/<skill>.json` for each skill it labelled (`results.py`): each host's label file entry whole, with the
round's name, attempt, commit, manifest hash, kit hash, reference host, price date and thresholds, and the name and
sha256 of `TAR`, the archive of the round's store folder. It refuses a round whose last attempt did not pass every
gate, or whose kit check named another kit than its manifest's. `TAR` must hold the round's store folder exactly,
every file with the same bytes and no other, so it holds every run, check and grade that recomputes each label.
Rounds are listed apart, never combined; the same round again replaces its entry. Labels from the phase 2 runner
stay under `phase_2_runner` for each host no round has run yet. Entries written before pressure situations were
labelled say `not_run: skill-fault gate`; a label now measures them itself (doc 11, Pressure situations).

Each entry also records the skill's hash and its previous version's (`skill_sha256`, `previous_sha256`), and the
setup the label file recorded (`setup`, `setups.py`): one fingerprint of everything that measured the skill, the
kit, cases with their worlds, situations, the other skills the skill's own cases install, the tools those cases
declare as each grading host's tools and drift probe found them, adapters, each host's version and model, the
graders, the runs, whether runs were pinned, the runner and the label rule, but not the skill itself. `rounds.py
results` is the one place that compares rounds: under `compared`, the results file sets each round beside the round
before it, and the command prints the list. Two rounds on the same fingerprint are the same setup; otherwise they
are "not comparable: setup changed", with the parts that changed named. An entry written before setups were
recorded has none, and the pair is unknown.

Each entry copies whether the round lists the skill as shipped (`shipped`), as the label file decides it
(`labels.shipped`): only when, on the reference host, its task label is `verified` and its trigger label is met (doc
12, Proven use). Each host's entry holds both, copied whole. A label file written before it decided this gives null.

Results files keep rounds in name order, its trailing number read as a number (`results.order`), and that order
picks the verified version a plan is held to. So a plan is refused unless its round's name sorts after every round
in each planned skill's results file (`versions.ordered`); planning the same round again is allowed.

## Cross-model grading

`regrade.py` grades every page a finished round graded again, once per grader route (doc 11, Cross-model grading).
It is no gate and writes no label. Run it at the round's commit:

```sh
python3 evals/harness/regrade.py ROUND --store DIR --route goose=MODEL@UPSTREAM [--route ...] [--attempt NAME]
    [--seed N] [--pages all|run|golden] [--graders 1|2]
```

It refuses a kit that is not the approved one, a changed case or adapter, and a page that does not hash as the
round's grade record says. Each route passes every probe and the grader faults before any route grades. Then each
route grades every page with two fresh graders, and the pass is written to `<store>/<round>/regrade/<pass>/`,
apart from the round's grades and labels. `--pages` and `--graders` grade fewer pages, or with one grader, to
stay in budget; `regrade.json` records the choice, and its `finished` time stays empty when the pass stopped.

Then report the pass. `--family` names a host whose runs a route's own model family made, so that pair's agreement
leaves those runs out and counts them apart:

```sh
python3 evals/harness/compare.py STORE/ROUND/regrade/PASS [--family HOST ADAPTER=MODEL ...]
```

It refuses a pass with no finish time, and writes `report.json` beside the pass.
