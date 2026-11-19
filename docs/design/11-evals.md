# 11 · Evals: the harness that measures skills

The eval harness measures each skill on each host by running the same tasks with the skill and without it. Every
run's world is declared up front and built from nothing, and nothing counts until the harness has proved, in that
same round, that it measures correctly. This document replaces the runner design of phase 2. The labels,
thresholds and portability rules of [10 · Skills](10-skills.md) stay as they are.

## Why the phase 2 runner was replaced

Phase 2 hit 24 measuring failures in a row. Each fix was right for its failure, and the next round still failed,
because the runner had four structural flaws:

1. **Deny-list worlds.** A workspace started as a copy of something bigger (the repository, the operator's
   environment, the host's defaults) and the runner stripped what it knew was dangerous. Each round found one
   more thing it had not stripped: `/tmp`, git history, project memory, the run's own expectations.
2. **Undefined arms.** "Without the skill" meant whatever was left after deleting the skill folder. Index rows,
   role files and loaded instruction files stayed, so the baseline was sometimes a stop test and sometimes
   contaminated, differently on each host.
3. **No proof of the harness.** Leaks were found after a full round, by a person or judge reading transcripts.
4. **Scoring outside the runner.** Most expectations were prose for graders spawned by hand, one per
   configuration, who knew which arm they graded and were never checked against known answers.

Only one of the 24 failures was a true finding about an agent. The other 23 were the harness measuring wrongly.

## Principles

1. **Allow, never deny.** A run gets only what its eval case declares. Nothing is copied from the machine and then
   filtered.
2. **One difference.** The two arms are built from the same world and differ only in the skill, proved by hash.
3. **Prove the harness first.** Every round starts with an audit, probes and planted faults. A miss stops the
   round before any real run counts.
4. **Scripts before judgement.** If a script can decide an expectation, a script decides it.
5. **Void only for harness faults.** A run is voided, and shown, only when the harness failed. What the agent
   did, including blocked attempts, is scored.
6. **A round is a record.** Every input is hashed, every output is stored outside the working tree, and a label
   comes from one complete round.

The runner and every check are Python 3 with only the standard library and no network calls of their own
(`HW-PORT-04`); the gate (Containment) only passes on a host's allowed connections. Judges stay independent of
the builder (`HW-PORT-03`).

## The baseline

The without-skill arm is the same project as if the skill had never been written. The project's own rules
(`AGENTS.md`, design documents, role files) stay in both arms. The lift therefore measures what the skill adds
beyond the repository's rules. A skill that adds nothing beyond them is a real finding: the skill or the rules
should change.

## Gates of a round

A round moves through fixed gates. Any gate that fails stops the round with its reason.

| Gate | What it does |
|---|---|
| Plan | Hash every input into the round manifest |
| Kit check | Refuse to start unless the measuring kit matches the judges' approval |
| Lint | Reject cases whose world or prompt is unsound |
| Probe | Prove each host's sign-in, powers, discovery, instructions and isolation |
| Faults | Run the judges' planted faults; every one must be caught |
| Run | Run both arms, sealed, cases and arms interleaved |
| Evidence | Reduce each run to one host-neutral record |
| Check | Script checks decide what they can |
| Grade | Blind, calibrated graders decide the rest |
| Label | Apply the labels of [10 · Skills](10-skills.md) |
| Store | Write the round outside the working tree |

## Worlds: what a run is given

Each eval case is a folder, `evals/skills/NAME/cases/<case>/`, holding `world/` and `case.json`. The skill is read
from `release/NAME/` when the release manifest lists it, and from `skills/NAME/` otherwise: a release skill is the
candidate, so it wins over an older skill of the same name.

- **`world/` is the whole project the agent works in, written without the skill.** It holds every file the run
  sees, including instruction files such as `AGENTS.md` and `CLAUDE.md` when the case wants them.
- **`case.json`** holds the prompt, the kind (`trigger` or `task`), where the skill goes (default `skills/NAME`),
  the index file and row format the world uses, the tools the case needs (such as `go`), the expectations, and for
  trigger cases the `train` or `test` split. It is checked against one schema before anything is built: a field
  outside the schema, or a value of the wrong shape, is refused with the reason. Every path in it stays inside the
  world. A document declared as copied names a file at the repository root, such as `AGENTS.md`: every folder
  holds skill text, its sources, the measuring kit or harnesswright's own formats, none of them project text. The
  copy is the source as git tracks it, with the table rows that name a skill removed, since the arm's index rows
  replace them. Every world path, and every text the run sees, follows the same one rule as `case.json`: ASCII path
  parts, and plain text with no control characters.
- **The with-skill arm is built by adding.** The runner adds the skill folder at its declared path, an index row
  generated from the skill's frontmatter, and a copy where the host discovers skills. The without-skill arm is the
  world exactly as written. Nothing is ever removed, so there is no list of lines to get wrong. A skill brings only
  the files git tracks in its folder, never a cache or draft left beside them. The manifest records both world
  hashes and the overlay.
- **The proof works from the case, not from the builder.** The expected manifest of each arm is rebuilt from the
  written world, the case and the skill sources, and the built arm must equal it entry for entry, the index file
  included. Each arm's `.git` must equal the one from writing that arm again in a scratch folder.
- **One description of a folder.** Every world, arm and output is described by one manifest: each folder, each
  file with its hash and executable bit, and each link with its target. A change to any of them is a change.
- **Trigger worlds install the full skill set** with its index, as in real use. Should-not-trigger queries
  include near misses that belong to a sibling skill.
- **Git history**, when a case needs it, is declared as commits in `case.json` and built with fixed authors and
  dates. What the harness adds, the installed skills and the index, goes into one setup commit with the same
  message, author and date in both arms. So `git status` is the same in both arms, and the logs have the same shape.

### World lint

The lint runs before any run. A case that fails it cannot run. It rejects:

- the skill's name or path in the without-skill world or in the prompt;
- an arm's name (`with_skill`, `without_skill`, `previous_version`) anywhere in the world, the prompt, the commits
  or the sibling skills, since a grader page shows them and would tell the grader its run's arm. A golden's changes
  and log are refused the same way when it is loaded;
- any run from the skill's **fingerprint**: every 8-word run of the skill's text, minus runs that also appear in
  verified copies of project documents, in installed sibling skills, in the skill's recorded upstream source
  (stored and hashed under `evals/skills/NAME/upstream/`), or in the standard licence texts recorded in
  `evals/fixtures/licences/`. Text the skill shares with the project's rules belongs
  to the project and stays in both arms. The prompt is never project text, since the case author writes it;
- any eval file, check, expectation text or results file inside a world;
- test-tell words such as "eval", "fixture", "grader" or "benchmark", unless that file allows the word. A judge
  also reads every world before it is approved;
- a `.git` folder, or a symlink that points outside the world;
- a document copied from this repository that is not its tracked source with the skill rows removed, or whose
  source has changed since it was copied.

## Containment: what a run can see

A run sees only its world, its scratch folder, its private home and temp folders, read-only system folders and its
host's own install. The runner proves this in every run.

- **One list of mounts.** A run sees exactly one list: the system program and library folders, the `/etc` entries
  a program needs to start and reach the network, the host's install and CA files (all read-only), the world, a
  fresh private home, a scratch folder in task runs, empty private `/tmp` and `/dev/shm`, a fresh `/proc` of the
  jail's own processes, a minimal read-only `/dev` and the gate's socket. Nothing in the operator's home is found
  for a host: one installed there runs only from what the operator names, and is refused until then. The jail
  has its own user, process, IPC, host name, cgroup and network namespaces. Its network holds only loopback, and
  the gate's socket is the one way out. Nothing else is mounted, so machine-wide host config such as
  `/etc/claude-code`, `/etc/codex` or `/etc/gitconfig`, the repository and the operator's home are never there to
  read. No mount may hold or sit inside the repository, or hold the operator's home.
- **The gate.** A proxy outside the jail passes on only `CONNECT host:443` to the host's model hosts: the
  adapter's `MODEL_HOSTS` and the host of each URL its `ENV_KEYS` pass on, such as a base URL. Anything else gets
  `403`, and every request is recorded with its answer. Every proxy variable in the jail names the gate. When the
  operator's machine has its own `http://` proxy in `HTTPS_PROXY`, the gate goes through it, so that proxy's
  address never enters the jail. A base URL on a port other than 443, or an IP address, is refused.
  Known limit: the host's commands share its network, so they too can reach the model hosts, and nothing else.
- **Visibility audit.** Before the host starts, a script runs inside the jail and checks it against the same list:
  every folder the jail creates holds only the way to the mounts below it, every folder the harness fills holds
  exactly what it put there (the world is the proved arm), no process outside the run is visible, the network
  holds only loopback, and the environment holds only the keys the harness built. Any problem voids the run and
  stops the round.
- **Canary tokens.** Unique tokens are planted where leaks came from before: a decoy operator home, the runner's
  temp folder, the repository checkout, other runs' folders. The audit scans the world, home, scratch, host install, CA
  files and host paths for them, reading every file, and every bundle is scanned for them.
- **Mechanism.** The default is `evals/harness/contain.py`: an allow-listed environment, a fresh private `HOME`
  and `TMPDIR`, and a `bwrap` jail built from the list. Any other containment that passes the audit, such as a
  throwaway container, is accepted, and the manifest records which was used. A machine with no passing containment
  cannot produce labels; its hosts are `not run`.
- **Bundled skills.** Each adapter turns off skills its host ships, where the host allows it, and records every
  skill the host exposes. An exposed skill that the case does not declare stops the round.
- **Secrets.** Every credential value the adapter passes is redacted from logs, transcripts and files before a
  bundle is written.

## Powers: what a run can do

Equal powers are defined once, in the runner (`evals/harness/powers.py`), for each mode. The jail enforces them
for the host and its commands alike, so each adapter turns its host's own sandbox off and removes every host tool
outside the table: nothing is left for the host to refuse. A sub-agent runs in the same jail, so it has the same
powers. Before any host runs, the powers probe tries every row
directly in the jail; any row that differs makes the host `not run`. Temp is the run's `TMPDIR`, `/tmp` and
`/dev/shm`, all private to the run. The probe reads the jail's own mount table from the kernel: every mount it
lets the run write must be a place the table lets the mode write, a device file such as `/dev/null`, or a kernel
view of the jail (proc, devpts). A failed direct connection alone proves nothing: the jail must have its own
network namespace with loopback only, and must not reach a listener the runner holds open on the machine. A model
host counts as reached only when the gate opens a tunnel to one.

| Power | Trigger runs | Task runs |
|---|---|---|
| Read | World and system folders | World, scratch and system folders |
| Write | Private home and temp only, never the world | World, scratch, private home and temp |
| Run commands | Yes, in the jail | Yes, in the jail |
| Network from commands | Only the model hosts, through the gate | Only the model hosts, through the gate |
| Host tools | Read, write, command, load a skill, start a sub-agent in the same jail, and wait | The same |

### Probes

Before real runs, each host passes these probes in each mode. A failed probe makes that host `not run` for the
round, with the probe's output as the reason. Each probe checks files the host wrote, never what the model says.
Probes get one probe-output folder that the host may write even in trigger mode. It exists only while probes run;
real runs never have it, and the powers probe proves that a trigger run can write nowhere else the table does
not allow.

1. **Sign-in:** a one-line prompt returns an answer.
2. **Powers:** the host runs the same probe script that tries every row of the power table, including `/tmp`, so
   its commands are shown to get the jail's powers. The outcome is read from the files it leaves.
3. **Discovery:** a probe skill, asked for by name with up to two tries, writes a token file.
4. **Instructions:** each instruction file in a probe world holds a token; the host writes back every token it saw,
   so every host is shown to load the same instructions.
5. **Memory:** a decoy memory planted outside the containment tells the host to write a token file. The file must
   not appear.
6. **Tools and drift:** the version of every tool a case declares, and the files a host writes for itself on an
   empty run, are measured and recorded per host version.

### Blocked actions and voids

Every action the host blocks is logged the same way on every host as `blocked`, with its reason, and scored through
expectations like any other behaviour. A run is voided only for a harness fault: a failed audit, a canary or
fingerprint hit, a host crash, or a host version that changed during the round. A voided slot gets at most one
remake. If that is voided too, the slot stays empty and the label is `inconclusive`, with the reason. The label
reports the void rate per arm with its counts; rates that differ between arms are reported, never a stop.

## Evidence: one record for every host

Each adapter turns its host's event stream into a host-neutral **action log**: files read, files written (with
content hashes), commands run (with exit code and bounded output), blocked actions, skill loads and the final
message. Every entry is tagged **observed** (the host reported it) or **inferred** (the adapter worked it out, such
as a file read parsed from a shell command). The runner adds a **world diff** that leaves out the host's measured
self-writes and both copies of the installed skill.

The evidence bundle holds the case, the arm, the diff, the files after, the action log, the final message, the
model, the host version and timings, plus a scrubbed transcript as evidence of last resort: the arm, skill paths
and skill loads replaced by neutral words, and credentials redacted. Every check and grader reads only the bundle.

Graders get a **grader view** of the bundle, never the full record. It leaves out both copies of the installed
skill, the generated index row, the host discovery copy and everything else the with-skill overlay added, from the
files after as well as from the diff. It shows each command as the command the agent ran, without its output or
exit code, since the two arms are different worlds and what a world prints back tells the arm; outcomes such as
"the tests passed" are decided by script checks on the full bundle. Every line that names the skill or its paths is
removed from the view's text. What the agent itself wrote or said about what it saw is its own output and stays
visible. The full bundle is kept for checks, audits and judges.

A judged question turns only on what the grader reads: every fact its pass or fail rule depends on is on the page
or written in the question. The page a grader reads therefore starts with the case's **request**, its prompt. The
prompt is the same in both arms, so it tells no arm, and the world lint keeps the skill out of it. A golden is
graded as a page of its case, so it gets the same request.

## Scoring

### Script checks

A library in `evals/checks/` decides what a script can decide: file state, sections and frontmatter, words shared
with a source, "ends with exactly one question", commands run or never run. A skill may add its own checks.

- **Every check has an answer key:** fixture bundles that must pass and must fail, run in the unit tests and
  approved by a judge.
- **Every check names its source:** a **contract**, a rule stated by a document in the world (cited by path and
  line, verified by the lint), or the **skill's own format**. Only contract checks and judged expectations count
  toward the lift. Format conformance is reported separately, and the with-skill arm's must meet its own floor.
- **A check never decides on inferred evidence.** It returns `undecidable`, and the expectation goes to the
  graders with the command list.

An expectation may be judged only when no check can decide it.

### Graders

Each judged expectation is a yes-or-no question with a pass rule, a fail rule, and at least one passing and one
failing example.

- **Graders are sealed runs** started by the runner, never by the session doing the work. Each sees one bundle,
  the expectations and their examples.
- **Blind:** the arm is removed, skill loads are neutralised, and runs from both arms are interleaved.
- **Two graders per run, on two different hosts** when both are available, so no model only grades its own host's
  output. A third grader breaks ties. Agreement is reported, not used as a gate.
- **The grader setup is calibrated, not each grader.** Golden bundles, built in the current world format with
  settled answers, are ordinary one-bundle grader runs, mixed in and indistinguishable from real ones. Golden
  accuracy for each expectation across the round is the gate. An expectation whose goldens are missed is marked
  unreliable, its runs stay ungraded, and the label is `inconclusive` and names it. Goldens are settled by an
  independent judge; the owner breaks ties.
- **Every grading file is validated** against its schema: every expectation answered, with evidence quoted.

### Baseline backstop

A without-skill run whose evidence holds a long passage of the skill's own text saw the skill, so it is void
(`backstop.py`). A hit is one unbroken span of at least 16 words, inside one text of the run (its final message, a
file it changed, a transcript line or an action log entry), in which every 8-word run is one the lint protects as
the skill's own. Matches in different texts, or the same words found again, never add up. A shorter match is a
phrase an honest agent reaches by itself, such as a common script header: it is listed beside the run's bundle and
in the run gate's report, never a void. The evidence is collected first, so a canary in it stops the round before
the backstop reads it. A void keeps the run's bundle beside its reason for a judge to read; the slot is made again
once, then left empty, as for any void.

### Cross-model grading

A measurement, not a gate: it gives no label. It asks whether graders of different model families grade the same
pages the same way. It takes one finished round and a list of grader routes, each an adapter and a model.

- **Same kit, same pages.** It refuses a round whose manifest kit hash is not the approved kit. It rebuilds every
  page the round graded, run and golden, from the stored bundles, and grades a page only when the page and its
  questions hash to what the round's grade record kept.
- **Each route proves itself first.** Every route passes the probes and the grader faults under that kit before
  it grades, as the round's hosts did; one that fails stops the pass.
- **Every route grades every page fresh,** through the same grader runs as a round, with the same prompt, quote
  check and tries: two graders a page, never read from the round's panel. Each grader's sheets, tries, seconds and
  token counts are kept, apart from the round's grades and labels, which it never changes.
- **What a pass keeps and leaves out.** It keeps each route's adapter hash, host version and pinned upstream, the
  kit (the round's, which the pass refuses to differ from), each grader's logs, and a finish time; a pass with no
  finish time stopped part way and is not read. It leaves out what hosts do not report: the upstream that served a
  try and the provider's settings. The model reported shows only as the keys of a try's token counts. The operator
  may grade one kind of page or give one grader a page, to stay in budget; the pass says which.
- **The report** (`compare.py`) reads one finished pass. A route's answer to a question is the one answer all its
  graders gave; when they gave two it is split, and when one gave none it is ungraded, both counted apart and
  never read as yes or no. Per route it gives golden accuracy, the agreement of its graders when it had two a
  page, the questions a golden miss leaves untrusted for it (by the golden gate's rule), every sheet it could not
  give with each try's reason, and its cost. Per pair of routes it gives agreement with counts and Cohen's kappa,
  each kind of page apart, and lists every disagreement. Runs made by a host of a route's own model family, as
  the operator names it, are reported apart for that pair, with the same figures. Every report states the limits
  that hold for every pass. The goldens alone are ground truth; agreement with the
  round's panel is concordance, not accuracy.

## Judges own the measuring kit and the faults

The **measuring kit** is everything that decides a label besides the agent: the checks and their answer keys, the
lint rules, the power table and probes, the goldens, the grader prompt and the fault catalogue
(`evals/faults/`). Independent judges approve it. The approval is a record of the kit's hash, written by a judge
session to the round store, where the builder's session cannot write. The runner refuses to start a round when
the kit's hash differs from the approved one.

### Harness faults

Every harness fault must be caught, or the round stops.

| Fault planted | Must happen |
|---|---|
| A copy of the skill or a canary outside the world | The audit and the canary scan catch it; no run sees it |
| A decoy memory naming the skill | The memory probe's token file never appears |
| Session, memory or credential values in the operator's environment | Not passed; redacted from every bundle |
| The skill's name, path or fingerprint in a without-skill world or prompt | The lint rejects the case |
| An eval file or a test tell in a world | The lint rejects the case |
| A run without the skill that copies a passage of it | The backstop voids the run, for the passage where it was put |
| A host-shipped skill exposed in a run | The round stops |
| A host that cannot run commands, or the containment, host or key missing | The probe fails and the host is `not run` |
| A file read through an unusual command, or a command that names a file without reading it | The entry is tagged inferred and no check decides on it |
| A golden bundle | Graders give its settled answer, or the expectation is marked unreliable |
| A grading file missing, repeating or misquoting an answer | The schema check rejects it |
| Two graders that disagree, or one with no answer sheet | A fresh tie-breaker answers only the split questions; a fresh grader of the same host stands in once for one with no sheet; one grader never decides alone |
| A view that names the arm or the skill | The page a grader reads names neither |
| A grader that writes to its folder or reads outside it | The jail stops every write and read; the grader's page, its folder and the folders beside it stay as they were |

Each fault is an entry of `evals/faults/harness.json`, planted where a seed chooses; its own gate runs unchanged,
and only the one outcome the fault names counts as caught.
The judges run the live faults themselves. They choose placements and names from their own seed, interleave the
fault runs with real runs, and decide from the stored evidence whether each was caught. Operator-home faults use a
decoy home, never the real one. The same faults run against a fake host in the unit tests of every pull request.

### Skill faults

Skill faults test that a skill degrades the way the rules say: `scripts: forbidden` in the profile, no Python
interpreter (the jail masks it), a command the host refuses (each adapter can deny a command pattern), a missing
input, and a host that cannot start an independent agent or a prompt that asks the agent to judge its own work.
They are their own gate: the with-skill arm must pass every fault case. They are not counted in the task pass rate
or the lift. A host that cannot plant a fault is `incomplete` for skills that need it.

After each round the judges look for ways the round could have been wrong, and add each one as a new fault.

## Rounds, results and labels

- **Plan.** `round plan` reads a plan file and writes a manifest with the hash of every world, case, skill,
  upstream source, kit part, adapter and host version. A host that does not report its model must have one named
  in the plan.
- **Run.** `round run` goes through the gates in order. Each run records its host version; a run whose version
  differs from the manifest is voided.
- **Resume by hash.** Each run is keyed by the hashes of its inputs and of the runner code that affects a run
  (containment, adapter, world builder, evidence). Only missing or voided runs are remade. Each label records the
  commits behind its runs.
- **Store.** Rounds go to the folder given with `--store`, outside the working tree, checked by writing and reading
  back a hash. The results pull request commits the manifest and every run's verdicts, redacted, so the label can
  be recomputed from the repository alone.
- **Label.** The labels and thresholds of [10 · Skills](10-skills.md) apply. If the reference host is not run,
  or its result is not settled, every other host is at most `inconclusive`. A task run passes when every contract
  expectation passed; format expectations are reported as format conformance, never in the pass rate. The
  with-skill arm's format conformance must meet its floor in [10 · Skills](10-skills.md), on top of the lift: a
  format expectation no check or trusted answer decided counts as failed, and a round that asked none is
  `inconclusive`. A judged format question is calibrated by goldens like any other, so a missed one keeps the
  label `inconclusive`. Trigger accuracy is that of the `test` split, scored in the with-skill arm. A skill load
  the adapter inferred from a read of the skill's `SKILL.md` counts, as in the discovery probe, since some hosts
  report no skill load of their own; the label names how many trigger runs rested on an inferred load only. A
  planned run that is not scored (void, empty or undecided) makes the label `inconclusive`, with the reason. The
  label file adds the void rate per arm, grader agreement, golden accuracy, the fault gate result, how many
  expectations rested on inferred evidence, and format conformance.
- **False done.** Every task case ends with one question it does not write, `evals/grading/done.json`: does the
  run say its work is done? The graders answer it, and goldens settle it, like any other question; no check decides
  it, and it counts in no pass rate. A run is a false done when its trusted answer is `yes` and a contract
  expectation failed. The label gives the false-done rate per arm, with its counts and the runs not decided.
- **Previous version.** A plan may name, for a skill it runs, the full commit of the skill's previous version.
  Its task cases then run in a third arm, `previous_version`, built like the with-skill arm but with the skill as
  that commit holds it. One reader (`rounds.previous`) takes it from a scratch worktree at that commit, and checks
  it against the manifest's hash for every run. A previous version equal to the one under test is refused. The
  label then requires the skill to be at least as good as its previous version on pass rate and false-done rate.
- **Cost.** Each run keeps its host's own token counts by model and its seconds; a host that reports no counts
  has none, never an estimate. Money is the counts priced by one dated price file, `evals/results/prices.json`,
  per model, with input at its price only where the cache did not hold it; a model with no price gives no money.
  The label names the price file's date.
- **Description tuning** keeps its train and test split. A tuned description is a declared, hashed input.
- **Labels from the phase 2 runner** stay in `evals/results/`, marked as from the old harness, until the first
  round of this harness replaces them.

## Build order

Each step is its own pull request, merged by the owner before the next starts.

1. This document.
2. Worlds, containment and probes: the world builder and lint, both arms with their hash proof, the visibility
   audit, canaries, config masks and redaction, the power table, the wider adapter contract (observed or inferred
   action log, blocked actions, bundled skills, fault planting), the probes, and the harness faults against the
   fake host. The judges approve the first version of the measuring kit.
3. Checks and cases: the check library with answer keys, both skills' evals ported to cases, and the skill faults.
4. Controlled grading: sealed graders, goldens, the grading schema and the grading faults.
5. Rounds: `round plan` and `round run`, the kit check, resume, `--store`, the new label file, and removal of the
   phase 2 flow (`--base`, `score`, hand grading).
6. The first labelled round of both skills on both hosts, checked by a fresh independent judge.

## Out of scope

Adapters for further hosts except goose (planned for cross-model grading), a containment for macOS, new skills,
and changes to the thresholds of [10 · Skills](10-skills.md).
