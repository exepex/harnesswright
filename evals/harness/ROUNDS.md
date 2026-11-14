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
`void.json` listing why, only for a harness fault: the host failed, or its version is not the manifest's. What the
agent did, a run that timed out included, is scored, never voided. A voided slot gets one remake; voided twice, it
stays empty. `void.json` stays beside a remade bundle, so the void rate per arm can be counted. A jail that fails
its audit, or a canary in any output, raises, and the round stops.

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
attempt's own folder (`<store>/<round>/grades/<attempt>/`). A check that breaks, a grader that breaks its jail or a
golden that cannot be built stops the round. Each gate's outcome, that of the gate that stopped the round too, is
written, as it ends, to the attempt record `<store>/<round>/attempts/<time>-<random>.json`, with the seed.
Everything a round writes or reports, its drift records included, passes one scrub: the canaries and credentials of
every containment its gates made, taken while its home is still there. Every gate, grading too, as goldens
calibrate only their own attempt's graders, runs again when the round runs again; only runs are kept.

The label gate (`labels.py`) gives each skill on each host one label of [10 ·
Skills](../../docs/design/10-skills.md), computed from the store alone: the attempt record, and for each kept or
made run its bundle, its `checks.json` and its trusted grades. One rule holds: a label rests only on settled
results. A task run passes when every contract expectation of its case passed, a check deciding first and a trusted
`yes` deciding what no check did; it fails when one failed, and is not scored when one has no trusted answer. Format
expectations do not count, as only the skill knows its own format. A trigger run, scored in the with-skill arm only,
passes when the skill loaded exactly when the case says it should. A load the adapter inferred from a read of the
skill's `SKILL.md` counts, as the discovery probe counts it, since some hosts (Codex) report no skill load of their
own; the label names how many trigger runs rested on an inferred load only. A trigger case passes when the skill
loaded in at least half its runs if it should trigger, and in fewer than half if it should not. Trigger accuracy is
that of the `test` split. A host that was not run, or a skill with no task case or no test trigger case, is
`incomplete`. Every planned run that is not scored (void, empty or undecided), too few scored runs, missed goldens,
no lift, or a reference host whose result is not settled make it `inconclusive`, each named. A missed threshold is
`unsupported`, each gap named. A skill whose round ran its previous version must be at least as good as it on the
same task cases: a pass rate below the previous version's, or a false-done rate above it, is `unsupported`, each
named; too few scored runs in that arm, or no decided false-done answer in either arm, keep it `inconclusive`. The label file goes to `<store>/<round>/labels/<attempt>.json`.

Beside each label, `measures.py` reports what it rests on, counted from the store and never estimated, each share
with its counts: the void rate per arm, grader agreement, golden accuracy from the goldens' grade records, the
faults the fault gate caught, how many expectations a check left undecidable on inferred evidence, format
conformance per arm with the expectations left undecided, and per arm the runs, seconds, token counts by model and
money at the price file, whose date the label file names. A run with no token counts, or a model with no price,
leaves its arm with no money, and the arm says how many runs had none. A voided try keeps no evidence, so the
cost names how many tries it leaves out.

Every task case ends with the done question (`evals/grading/done.json`), appended by `cases.Case`: does the run say
its work is done? It is graded and calibrated by goldens like any other question, and counts in no pass rate. The
label gives, per arm, the false-done rate: runs whose trusted answer is `yes` while a contract expectation failed,
of the runs where both are decided, with the runs not decided counted apart.

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
