# Eval harness

The ground-up eval harness of [11 · Evals](../../docs/design/11-evals.md). It replaced the phase 2 runner, which
was removed once rounds ran here.

The harness is built in small pull requests, one part each. This folder holds the first parts: **the manifest,
eval cases, skill reading, building and proving the two arms, the world lint, containment, the network gate,
the power table, the host contract, with a fake host, the probes, the scrub, the evidence bundle, the grader view
and the harness faults**. The rest of the fault catalogue and the measuring kit come next.

Python 3 standard library only, and no network calls of its own (`HW-PORT-04`): the gate only passes on a host's
allowed connections.

## Parts

| File | Does |
|---|---|
| `manifest.py` | The one description of a folder: every path with its kind (folder, file, link), mode and hash |
| `cases.py` | Reads `evals/skills/NAME/cases/<case>/case.json` and checks it against one schema |
| `skills.py` | Reads a skill folder and its frontmatter, and checks that a folder holds only allowed entries |
| `world.py` | Plans and builds both arms of a case, and proves each is exactly what the case says |
| `internal.py` | Builds an internal skill's world: the kit's allow list at its pinned commit, without the skill under test, its release rebuilt and checked, with the case's own files on top |
| `teamnotes.py` | Holds a team world's notes to the team's own rules: no harnesswright rule ID or rule text outside `.harness/` |
| `lint.py` | Rejects a case whose world or prompt is unsound, from one list of what the run can see |
| `textruns.py` | Text as the lint reads it: folded words and runs of consecutive words |
| `contain.py` | Builds one run's environment, home and jail from one list of mounts |
| `audit.py` | Runs inside the jail before the host starts and checks it against the same list |
| `gate.py` | The jail's one way out: a proxy that passes on only the host's model hosts |
| `powers.py` | The power table of each mode, and the probe that proves the jail gives exactly that |
| `host.py` | The one contract between the harness and a host's adapter, and the one place a host runs |
| `probes.py` | The probes each host passes before real runs, and the tools and drift record |
| `scrub.py` | The one way out of a run: a canary stops a value, then every credential is redacted |
| `evidence.py` | Turns one run into a bundle: a scrubbed record and blobs named by their hash |
| `view.py` | The grader view of a bundle: allowed fields and paths only, the same in either arm |
| `faults.py` | Plants each fault of the catalogue, `evals/faults/harness.json`, and runs the gate that must catch it |
| `look.py` | Runs a harness program inside a run's jail, to see what the run can see, whatever its host did |
| `host_faults.py` | The faults of a host, its memory and its log, planted and run by the rule of `faults.py` |
| `grading_faults.py` | The faults of grading: a sheet, the goldens, a split panel and the view, planted on the repository's goldens by the rule of `faults.py` |
| `grader_faults.py` | The faults of a grader's own run: a grader that writes to its folder or reads outside it, run through `grader.grade` in the jail |
| `checks.py` | The one way a script check decides an expectation from a bundle, and its answer keys (`evals/checks/`) |
| `kit.py` | The measuring kit's files and hash, the judges' approval record, and the kit check |
| `grading.py` | What goes to graders, the one page a grader reads, and the check of an answer sheet |
| `grader.py` | One sealed grader run, the panel of graders of a page, and the blind order of a round's pages |
| `goldens.py` | Hand-made runs of a case with settled answers, built as runs, and the golden gate |
| `rounds.py` | A round's plan file and its manifest: the hash of every input and each host's version, written once to the store |
| `gates.py` | `round run`: a planned round through its gates in order, the first that fails stopping it, each outcome in the attempt record |
| `extras.py` | The extra runs gate: 3 more runs of each split case a too-close measure or floor reads, capped by the plan's `extra_runs` |
| `agreement.py` | Grader agreement per judged question over every page and answer, and the questions to rewrite |
| `grades.py` | The grade gate: what no check decided, answered by blind panels with the goldens mixed in, trusted only where the goldens were |
| `runs.py` | One run of a round, named by the hash of its inputs, stored once, kept on resume, and void only for a harness fault |
| `backstop.py` | The baseline backstop: a without-skill run holding a long passage of the skill's own text is void |
| `labels.py` | The label gate: each skill's label on each host, by the thresholds of 10 · Skills, from what the round stored |
| `verdicts.py` | The task verdict: a task run's outcome, a skill's measures on one host, and its task label by its kind (`evals/kinds.json`), with each gap and doubt named |
| `triggers.py` | The trigger label, a line apart from the task label: whether a trigger run loaded the skill exactly when it should, and the test split's accuracy against its threshold |
| `measures.py` | The label file's other measures: void rate, pinned-load rate, golden accuracy, faults, inferred evidence, format conformance, and cost per arm |
| `versions.py` | The verified version a plan is held to: a skill changed since it, with a task case, runs it as `previous`, and a round name sorts after every round its skills recorded |
| `results.py` | `round results`: a finished round's labels copied whole into `evals/results/<skill>.json`, named by its manifest, kit and archive |
| `setups.py` | One setup: the fingerprint of everything that measured a skill in a round, except the skill, and the parts in which two setups differ |
| `regrade.py` | Cross-model grading: every page of a finished round graded again by each grader route, after it passed its probes and grader faults, apart from the round's grades |
| `compare.py` | The cross-model comparison report of one finished regrade pass: per route golden accuracy, grader agreement, untrusted questions, refused sheets and cost; per pair agreement, Cohen's kappa and every disagreement |
| `prices.py` | What a run cost: its token counts by model, priced by the one dated price file |

## Commands

Run from the repository root.

```sh
# Unit tests. The jail tests need Linux and bubblewrap (`apt-get install bubblewrap`); without them they are
# skipped and say why.
# No bytecode: the kit's folders hold only what git tracks (see "The measuring kit").
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s evals/harness/tests
```

## How a case is checked

`cases.SCHEMA` lists every field `case.json` may hold, each with the one shape it may take. Each shape is a
pattern of what is allowed. Anything else is refused with the reason, so a malformed case stops before a world is
built instead of failing part way:

- every path is relative: parts of ASCII letters, digits and `. _ + @ -`, joined by `/`, never `.`, `..` or `.git`.
  World entries follow the same path rule, so any of them can be committed, linked to or given `allow_words`;
- every text is plain: no control character other than tab, line feed and carriage return. World files, the prompt,
  commit messages and the index row all obey this one rule (`cases.is_plain`);
- a trigger case needs `should_trigger`, `split` and `index`; a task case may not have the first two;
- a commit needs a non-empty message and a list of paths;
- a copy names a source that is a file at the repository root, and its 64-character sha256;
- an index row may use only `{name}`, `{path}` and `{description}`, with no index, attribute or format spec;
- an expectation is `{text, source, judged}`, with a `check` when a script can decide it (doc 11, Scoring).
  `source` is `"format"`, the skill's own format, or `{"contract": {"path", "line", "quote"}}`, a rule a world
  document states. `judged` is `{question, pass, fail, examples: {pass, fail}}`, a yes-or-no question for the
  graders with its two rules and at least one example of each; every expectation has one, since a check that cannot
  decide sends its expectation to the graders. `check` is `{name, args}`, a check of `evals/checks/`;
- a tool is a command name;
- siblings are distinct skill names, never paths and never the skill under test;
- `allow_words` keys are world paths, `<prompt>` or `<commit N>` for a declared commit.

## How a skill is read

`skills.py` works from four rules, each a list of what is allowed.

`skills.folders` is the one list of the repository's skills, name to folder: each `release/<name>/` the release
manifest lists, and each other folder of `skills/` whose `SKILL.md` git tracks. A release skill wins over one of
the same name in `skills/`, as it is the candidate a round measures. Every gate, the run key, the world builder and
the lint take a skill's folder, and the list of skills, from it.

`skills.frontmatter` reads one stated subset of YAML, with only the fields of `HW-PORT-01`: `name`, `description`,
`license` and `compatibility` hold one plain line, and `metadata` holds `  key: value` lines whose keys are
lower-case words joined by `-` and whose values are plain lines, or, as the release build writes them, text in
double quotes with no quote, backslash or control character inside. A plain line is words separated by single
spaces, which YAML reads as exactly the text written, as it reads such a quoted value as its inside. There are no
other quoted values, block scalars or comments, and a value or
key spelled like a YAML null, boolean, number or date is refused. Each field appears once, lines end only at a
newline, no other control character is allowed, and the block ends at a line that is exactly `---`.
Anything else is refused with its line number, so a value is never read short or as the wrong type: the index row
and the fingerprint are built from it. The frontmatter name must be a skill name, and the expected one when the
caller names it, because the name chooses where a host discovers the skill.

`skills.structure` allows folders, regular files and relative links whose target is made only of `..` and name
steps, and leads step by step through real folders to a real folder or file inside the folder. A link is judged by
its text against the folder's manifest, never by resolving it on disk, so a link through another link, or one that
leaves and comes back in through the folder's own name, is refused. A `.git` folder is never allowed, and every
path follows the path rule of `case.json`.

`skills.tracked` is what a skill is: the files git tracks in its folder, staged ones included. `skills.skill_files`
reads only those, and each must be a regular file reached through real folders, never a link. `skills.skill_names`
reads which skills exist from the same list: each folder whose `SKILL.md` git tracks. So a cache, a virtual
environment or a draft skill on disk never enters an arm and never decides whether a case can be built. A skill
folder git does not track, such as a candidate copied to a temporary folder, is refused until it is added.
git reads the checkout with no system or global config, so the operator's settings never take part. git's own
refusal of a checkout owned by another user is kept: run as the owner of the checkout.

## How the arms are built and proved

`world.plan` works out, from the case, the adapter and the skill sources alone, which skills an arm installs and
where: each at its declared path and at the host's discovery path, with its index row. It refuses a plan that
would overlap the world or another skill, a discovery path outside the arm, an index file that is not a regular
file, and a trigger case that does not install every other skill as a sibling.

`world.build` makes one arm from the world: the world as written, its git history, and the arm's installs, the
siblings and, in the with-skill arm, the skill. A skill brings only its tracked files. The index is written in one
step from the written world with every row of the arm, as the proof expects it. It is edited as bytes, so its
encoding and line endings are kept. When the world has a history, the installs and the index go into one setup
commit, with the same message, author and date in both arms, so `git status` is the same in both arms and the
logs have the same shape. Every entry of an arm then gets one fixed time, so no file looks newer in one arm than in
the other.

`world.prove` reads both arms from disk again. It rebuilds each expected manifest from the written world and the
plan, never from what the builder recorded, and each arm must equal it entry for entry, the index file included.
Each arm's `.git` must equal the one from writing that arm again in a scratch folder. Without
commits there is no `.git` of any kind, link, file or folder. With them, every entry under `.git` must match byte
for byte, the index included: it is rebuilt from the head tree with no file times or flags, so every copy holds the
same bytes. git never runs on an arm to prove it.

Git runs with an allow-listed environment and an explicit git folder, so the operator's `GIT_DIR` or hooks never
take part. Declared paths are added with `--force`, so a world `.gitignore` cannot drop them, and a git failure is
a case error.

## How a case is linted

`lint.lint_case` lints a case as it will run. It builds both arms with the skill folder the run uses, such as a
candidate version, proves each is exactly what the case says, and only then reads the without-skill arm.
`lint.lint_skill` does this for every case folder of a skill, one at a time, so a case that cannot be read or built
is listed with its reason and the others are still linted.

`lint.visible` lists every place the without-skill run can see. Every rule reads this one list. A place has a kind:
`world` (a world entry: its path, and its text or link target, copies included), `declared` (the prompt, a commit
message, or the index row the case writes), `installed` (a file of an installed sibling skill) or `rows` (the
siblings' index rows as the run reads them: the case's template filled with each sibling's name, path and
description). `lint.RULES` says which rules read which kind. `world` and `declared` places are what the case
author wrote, so every rule reads them. `installed` places are read for the skill only. `rows` mix the two, so
every rule but the tells reads them: a text split between the template and a sibling's description is still found.

Every world file must be UTF-8 and plain text (`cases.is_plain`); anything else, such as UTF-16, an archive or a
binary, is refused rather than guessed at. Text is matched on words after Unicode compatibility folding, with
format characters such as soft hyphens removed.

Every text rule is one rule: protected text, minus project text, found in a place. Project text is computed once:
verified copies, installed sibling files, the recorded upstream source and the standard licence texts recorded in
`evals/fixtures/licences/`. A skill and a world may carry the same licence, but only its standard terms are
excused, never a file by its name. That text stays in both arms, so it never counts. The prompt is never project
text, since the case author writes it for this case.

- In every place: the skill's name, as words or squashed into one word (`HaikuWriter`), plural or not, its custom
  path, and any 8-word run of the skill's own text. A sibling skill's own file that names the skill is reported
  against the sibling, because skills never name each other.
- In `world` and `declared` places: each word that starts with a tell stem, unless `allow_words` names that exact
  word there (the index row has the index file's); any 8-word run of eval text; and any run of an expectation, in
  any place but the prompt, which may ask for it. An expectation of three to five words is matched whole. One of
  one or two words cannot be told apart from ordinary project words, so the judge who reads the world looks for it.
- Eval text is text about skills and their cases, which tells an agent what is measured: every file under
  `evals/` but `evals/harness/`, the general machinery, which says nothing about a skill, and `evals/results/`,
  the counts and labels the harness writes after a round, which hold no case's prompt, question or answer. A new
  kit part counts without being listed. `evals/fixtures/` and a skill's `upstream/` and
  `cases/CASE/world/` folders hold project text and are left out. Python is read for its strings, f-string text
  and comments only, since its code is the same in any Python program. So a check copied with its strings and
  comments removed is not caught here; the judge who reads the world is the check for that.
- Case data (every `case.json` under `evals/`, and the case's own wherever it lives) may
  repeat what the run sees of the case outside its world (its prompt, commits and index row) and its world's paths.
  Other eval text may not.
- A golden (`evals/goldens/SKILL/CASE/NAME.json`) is a run on its case's world, so what it reads and quotes of that
  world and the case data is the case's own text. Its eval text is the rest: each 8-word run of its text values
  that its case's world and case data do not hold, such as the claims it writes (`lint.golden_said`).
- Every text of an expectation is expectation text: what it says, and its judged question, rules and examples.
- Each contract is found where it is cited: its quote, of at least three words as the lint reads words, starts on
  line `line` of the world text file `path`, never a link, and may run on over the lines after it. A quote excuses
  only itself, by its words: the case data file that cites it may hold it, and the expectation that cites it may
  restate it. Each check names a check of the library, with arguments that fit its list (`checks.validate`, the
  test `decide` runs too).
- A copy is verified when its source is a regular file git tracks in the repository, spelled exactly as git
  tracks it and reached through real folders; the source still has its recorded `source_sha256`; and the world file
  is the source with its skill rows removed. A skill row is a table row that names a skill of the repository: the
  arm's index rows replace it, so a real `AGENTS.md` can be copied. Any other copy is a finding, and its text is
  not project text.

A world that cannot be built, such as one with a `.git` folder or a link out of it, fails with the builder's
reason. The history is built with no git templates, so `.git` holds only what the case declares.

## How a run is contained

`contain.Containment` sets up one run: a fresh `home/` with copies of the adapter's `CREDENTIAL_FILES`, a
`scratch/` in task runs, and an environment built from the allow list. `Containment.mounts` is the one list of what
the run sees, and `Containment.jail` builds the `bwrap` command from it. A host in the operator's home runs only
from the `host_paths` the operator names. `Containment.audit` runs `audit.py` in the same jail, after `manifest.py`'s
source, and checks the jail against the same list (doc 11, Containment). Any problem raises `ContainmentError`.

The jail has no network but loopback. `Containment.gate()` starts the run's gate on `gate.sock` in the run folder,
and every jail of the run runs inside it: the jail's first program, `gate.FORWARDER`, listens on
`127.0.0.1:3128`, passes each connection to the gate's socket, and starts the host with every proxy variable set
to it. The gate allows only `CONNECT` on port 443 to `Containment.hosts`, records each request in `log`, and goes
through the operator's own proxy when there is one.

## The power table

`powers.TABLE` is the one statement of what a run may do: each row is an action, with whether it must work in a
trigger run and in a task run. `powers.probe(run)` runs `powers.PROBE` in the run's jail, inside its gate, and raises
`PowersError` naming every row that differs (doc 11, Powers). Each write makes a file with a unique name and removes
it again, so the world stays the proved arm. The places a mode may write are one set, from the table: the private
home, `/tmp`, `/dev/shm`, the world and scratch in task runs, and the probe-output folder in probe runs. "Write
outside the run" reads the jail's mount table from `/proc/self/mountinfo`: any other mount the kernel lets the run
write is named, unless it is a device file or a kernel view (proc, devpts). The jail remounts its root and `/dev`
read-only for this. "Connect directly" works when the jail shares any of the machine's network: the runner's network
namespace, an interface other than loopback, or a listener the probe holds open on the machine's loopback. So it never
rests on an outside address failing.

## The host contract

`host.CONTRACT` lists every name a harness adapter defines, and `host.check_adapter` checks them when the adapter
is loaded. `adapter.jail_command` turns the host's own sandbox off (the jail enforces the table), turns its bundled
skills off where the host allows it, and keeps only the tools in `adapter.TOOLS`, each named with a kind of
`powers.TOOLS`. `adapter.pin(skill, path)` gives the lead line of a pinned task run; `host.lead` takes it only as one
line that names the skill and its path, so the grader view removes it. `host.run` is the one place a host runs: in
the run's jail, after the audit and inside the gate.

It checks what comes back against two allow lists. The action log may hold only the entries of `host.ENTRIES`:
reads, writes with content hashes, commands with exit code and whole output, actions refused by the host or the jail
(`blocked`, with the reason), skill loads, sub-agents and messages, each tagged `observed` (the host reported it) or
`inferred` (the adapter worked it out, such as a file a shell command reads). The host may expose and load only the
skills the arm installs, and expose only the adapter's tools. A host that ran must report what it exposed: no report
is never read as "nothing". Anything else raises `HostError`, and the round stops. The jail's audit runs first, and
a host that crashes or times out is a `failure`: the run is void. The host's own token counts by model
(`host.TOKENS`) are kept with the run, or none when it reported none. `prices.cost` prices them by the dated price
file `evals/results/prices.json`; a model with no price, or a run with no counts, has no money, never a guess.

`tests/fakehost/` is a fake host and its adapter: a program with no model that carries out a list of actions, with
its own sandbox, a bundled skill and a tool beyond the table, as a real host has. The tests run it in a real jail,
so the contract and its faults are shown end to end in every pull request. The Codex and Claude Code adapters give
it too ([adapters](../../adapters/README.md#the-harness-contract)).

An adapter reports a write that failed as `failed`, and `host.run` decides what it was from the jail's own mount
list: when the nearest mount above the path is not writable, the jail refused it and it is `blocked`; otherwise it
is left out, as the world diff shows. Paths inside the world are logged relative to it, on every host. An
adapter's `RUN_ENV` holds fixed variables it sets for every run; they are never taken from the operator. Its
`memory_files(home, world)` names where its host reads memory and the user's own instructions outside the world,
for the memory probe. The containment refuses a mount in or above the operator's home, which is both the
`operator_home` it is given and the real one.

## Probes

A probe is a probe world, a prompt and a check (doc 11, Probes), with one rule: the file the probe asks for is right,
and the host's own report, its exposure and action log, shows it did what the probe tests, not a way around it. A
probe of a host action allows only the actions it asks for (`probes.ALLOWED`): any other log entry fails it. The
check never reads what the model says. `probes.probe(adapter, name, mode, root)` runs one probe through `host.run`,
in a containment made with `probe=True`, and returns why it failed, or `None`; `probes.probe_host` runs every probe
in both modes, and the tools and drift probe, and returns the reasons the host is `not run` and the drift record.
The probe-output folder is the one place a probe run
may write beyond the table, in both modes; real runs never have it, and `powers.spec` adds it to the places the
powers probe allows only when it is there. A file there is read only when it is a regular file, so a link the host
made is never followed out of the jail.

- **Sign-in:** the host writes `ready` into `sign-in.txt`.
- **Powers:** the host runs exactly the one command it is given, which runs `powers.PROBE` with the spec the harness
  put in the folder, and nothing else; its output, which must carry the spec's nonce, is checked against the table
  with `powers.check`. So its commands are shown to get the jail's powers, and a result written by hand fails.
- **Discovery:** asked for the probe skill by name, with up to two tries, the host exposes it, loads it and writes
  the token that only the skill's `SKILL.md` holds. A host that found the file some other way fails.
- **Instructions:** the host writes back the tokens its instructions give it, and may do nothing but write what it
  already knows: no read, no skill, and no command that does not carry the token. The probe world has an `AGENTS.md`
  with one token and a `CLAUDE.md` that imports it, so every host must report exactly that one token.
- **Memory:** the host writes `ready` into `memory.txt`, while a decoy memory sits in every place the adapter's
  `memory_files` names: a decoy operator's home, holding only copies of the credential files, and the folder above
  the world, planted before the run's home is built from it. Each decoy asks for its token in `remembered.txt`. The
  token is a canary, so the audit refuses a jail that can see a decoy, even one in a credential file. The probe also
  fails before the host runs when a mount lets the run see a memory place of the given operator's home or the real
  one, such as a host path the operator names in their home. After the run it fails when the folder holds any file
  but `memory.txt`, or the log the token. An adapter that names no memory place is refused.
- **Pinned load** (`probes.PINNED`, task mode only): the prompt starts with the adapter's lead line for the probe
  skill (`host.lead`), and with up to two tries the host's log must prove the load by `evidence.loaded`. The probe
  gate pads the probe skill with neutral lines to the longest `SKILL.md` the round installs, its previous versions
  too (`gates.installed`, `probes.length`); a caller that gives no length probes the short skill.
- **Tools and drift** (`probes.drift`): no pass or fail of its own, only a record. An audited jail runs
  `probes.TOOLS_PROBE` for the host's program and each tool a case declares: where the run finds it, its hash and its
  version line, or `null` when the run has none. Then the host has an empty run in each mode, and every file it
  added or changed in its home, scratch and world is listed. A host that fails that run is `not run`. Comparing
  records between host versions, and storing them, belongs to the evidence step.

Every token is fresh for each run. A host or containment that breaks its contract raises, as in any run.

## The scrub

Every value a run's evidence keeps passes one `scrub.Scrub` (doc 11, Evidence), which sees the whole raw value
first: a canary token stops it (`scrub.Leak`, the run is void), then every credential is redacted in every form
output may hold it (as written, JSON-escaped, URL-encoded and decoded). So nothing is cut before it: the action log
and the gate's log keep whole outputs and request lines. `scrub.credentials` is the one rule of what a credential
is: each `ENV_KEYS` value, the secret part of a URL (its password with `user:password`, or its user when it has no
password), each decoded, and a credential file's strings of at least 8 characters. A named credential must be 8 or
more letters, digits or `-_.~+/=`, so the scrub knows every form it can take; any other cannot be redacted reliably
without damaging the evidence, so the containment refuses the run. The scrub runs only on what the run
made, never on what the harness made, such as hashes and field names (`Scrub.value` keeps keys, `Scrub.names`
scrubs keys the run chose). A reason the harness reports never repeats a token or credential (`Scrub.quiet`).

## Evidence

`evidence.collect` turns one run into a bundle, after the run, through the run's scrub. It reads the world after
the run once into a manifest (a pipe or socket the agent made is an `other` entry), and stores each file as a blob
named by the hash of its scrubbed bytes, so no name the run chose touches the disk and nothing in a bundle is a link.
The world diff against the proved arm leaves out the host's own files (those paths only) and both copies of the
skill with the folders above them, the same in both arms. In the action log, a value the harness chose
(`host.FIXED`: kind, source, a write's hash) is kept when it passes its test; every other value is scrubbed. Home and
scratch are scanned for canaries, and anything the scan cannot read refuses the run. The bundle keeps command output
whole and cuts request lines only after the scrub. `evidence.store` writes a new folder outside the repository, and
`evidence.load` reads it back, refusing missing, extra or changed blobs. The module docstring gives each rule in full.

## The grader view

Graders see `view.view` of a bundle, never the full record, which stays for checks, audits and judges. The view is
built by allow lists and four rules, each applied the same way in both arms, so the same run in either arm gives
the same view. Fields and paths: only `view.FIELDS` (no arm, host, model, timings, exposure, requests or
transcript), and only world paths outside the overlay and the host's own files. Actions: a log entry is dropped
when it loads the skill or its path, command or refused action names the skill. What the agent did, not what the
world showed it: a command is shown as the command the agent ran, without output or exit code, since the two
arms are different worlds. Text: in every text the view shows, each line that names the skill or its paths is
removed (the index row with it, however edited or copied), and the run's folders become neutral words. The diff is
the diff of the view's own entries. A run's folders must never name its arm.

## Grading

A grader answers only what no check decided, from the grader view only, and every answer is checked against that
view. `grading.questions` sends an expectation to the graders when it has no check or its check gave `undecidable`,
so a grader never overrules a check. `grading.page` writes the one page a grader reads from the case's request and
`view.view`: the request, the final message, the actions with each field as the agent wrote it, the changes and the
files. A grader is a trigger run (`grader.grade`) of a folder that holds only that page and the questions, with the
grader prompt `evals/grading/prompt.md`: it can read the folder and write nothing the harness reads. A grader starts in its folder
and sees its whole path, so `grade` alone chooses it: a new folder of random name in the operator's temp folder, the
same for every page, removed after the run once all it made outside the folder has passed `evidence.reported`, the
one way every run's output is scrubbed and checked for canaries. Its final message is its answer sheet, one JSON
object, alone or in one fenced block. `grading.check` accepts the sheet only when every question is answered once
with `yes` or `no` and each quote is on the page word for word: its words (runs of letters and digits, case kept)
are a run of the page's words, and punctuation, Markdown marks and white space only separate words. A host
failure or a refused sheet gets one more try (`grader.TRIES`); then that grader is ungraded. `grader.blind` gives the
pages of a round, both arms and the goldens, in an order mixed by a recorded seed, each with an opaque id, the hash
of its page. The answer keys of `grading.check` are in `evals/grading/keys/`.

Each page is graded by a panel (`grader.panel`), by one rule: a question's answer is the one two graders gave. Two
graders grade the page, on two different hosts when both are available. A question they answered two ways goes to
one fresh grader on the reference host, Claude Code. An ungraded grader is replaced once by a fresh grader of its
own host, which answers every question, so the two sheets still come from both hosts. A question with no two answers
the same, as when that grader is ungraded too, stays unanswered, so the run is `ungraded` on it: one grader never
decides a question alone. How many
questions the two graders answered the same is reported, never used as a gate.

A golden is a hand-made run of a case with a settled answer for each expectation,
`evals/goldens/<skill>/<case>/<name>.json`, written by a judge and never by the builder. It holds the run's
`changes` to the case's world, its `log`, whose last message is the final message, and `settled`, one `{expectation,
sha256, answer, by}` per question id. `sha256` is the fingerprint of the whole expectation (`goldens.fingerprint`),
so a golden never settles an expectation that moved or changed in any way. `goldens.bundle` makes it a bundle the
way every run is made one: the case's without-skill world built for the round's host, the golden's changes written
into it, and `evidence.collect` reading it with the golden's log and the case's real overlay. From there it goes the
way of every run, through the checks, the grader view, the page, the blind order and the panel, so nothing tells a
grader it is a golden. `goldens.gate` is the golden gate, by one rule: an expectation's grading is trusted in a
round only when every golden got its settled answer, with at least one settled `yes` and one settled `no` among the
goldens it was asked of. One miss, or a question left unanswered, marks it unreliable, with the reason, and no
golden can be left out of the gate.

## Script checks

`checks.py` is the one way a script check decides an expectation (doc 11, Script checks). A check is a function of
the full bundle and its arguments that returns `pass` or `fail` with a reason, or `undecidable`. The checks are the
`CHECKS` of the modules in `evals/checks/`, each with an allow list of its arguments; arguments outside it, an
unknown check, or a check that breaks raise `CheckError`, and the round stops. A check reads the bundle only through
`checks.Bundle`: the files after and the world diff, which the harness made, the final message, and the action log
by kind. That door refuses inferred evidence: when an entry of a kind the check reads is tagged inferred, the check
is `undecidable` and the expectation goes to the graders.

Every check has answer keys in `evals/checks/keys/<check>/`, at least one that must pass and one that must fail. A
key holds the check's `args`, the `outcome` it must give, and the run it is given: the world files `before` and
`after` ({path: text}), the `log` and the `final_message`, made into a bundle the way `evidence.collect` makes one.
The unit tests run every key, and a stored bundle is decided as its key is.

| Check | Decides |
|---|---|
| `file_state` | The file at `path` exists, is absent, is unchanged, or was changed by the run |
| `changes_only_in` | Every path the run changed matches one of the `allowed` globs (`*` crosses folders) |
| `lists_every_change` | The run's `file` names every other file the run added or changed by its own whole path |
| `command_ran` | A program matching `pattern` where it starts ran, or was never run nor tried (`ran`), maybe with its own `exit_code` |
| `sections` | The Markdown headings of `level` are exactly `headings`, in order |
| `frontmatter` | Each line is a field given once or part of one: `required`, only `allowed`, with `values` |
| `ends_with_one_question` | The text holds exactly one question, and ends with it |
| `shares_words` | The text shares a run of `run` words with the world file `source`, or none (`shared`) |
| `no_shared_words` | No file the run wrote in the `written` globs shares a run of `run` words with the world file `source`, or only with its `lines`, read as one text |
| `field_words` | The frontmatter field `field` holds at most `most` words |
| `line_counts` | The `section` lists only `` - `path` (N lines) `` or `(deleted)` lines, each true |
| `line_references` | Each `` `path:N(-M)` `` span of the writer's own prose that names the world points at real lines |
| `cites_listed_ids` | The text cites at least one ID matching `pattern`, and every one is listed in the world file `index` |
| `rule_tags` | The skill `folder`'s template and its other `.md` files hold rule tags only on `Rules:` lines and no bare ID; they tag at least one rule, every tag is in the world file `index`, and each `require` group has one tagged |

The text checks read the world file `file` after the run, or the final message when `file` is left out. A text
that does not exist fails. Those that read Markdown read it through one reader, `text.lines`, which gives every
line one kind: frontmatter, fenced code or prose. `shares_words` reads only words, and it reads the source after
the run, so a case pairs it, and `no_shared_words`, with `file_state` `unchanged` on the source.

`rule_tags` keeps its own reader of rule tags (`evals/checks/tags.py`), apart from the build's and the release
check's; all three are tested against the same bad lines, `v2/build/tests/golden/tag-faults.md`.

## Harness faults

`evals/faults/harness.json` is the catalogue of harness faults (doc 11), part of the measuring kit; each entry names
one plant of `faults.plants()`. `faults.run(fault, setup, seed)` plants it where the seed chooses and runs the
harness's own gate unchanged (the lint, the audit, or a whole run, whose bundle it stores and lists). It is caught
only by the one outcome its plant names; anything else is a miss. Refusing plants run a clean control first, a
lint fault must be refused by its own rule, and every reason passes one scrub. A fault that stops its run before
a bundle exists (`exposed`, `not run`) is caught with what its gate saw (`faults.Caught`), which the result keeps
as `seen`, scrubbed the same way, so the judges can check each catch.

| Fault | Places | Caught when |
|---|---|---|
| `outside` | beside the run's world, a decoy operator home, another run's folder, the machine's temporary folder, the repository checkout | A canary and a copy of the skill holding one are planted there; the harness looks for each from inside the run's own jail and finds none, and the run passes its audit, does not fail, and keeps every canary out of its output. What the host chose to look at never decides it |
| `inside` | the world, a host path, a credential file from a decoy home | The audit refuses the run for the canary, and passes the same run without it |
| `environment` | the operator's environment | The harness dumps the environment from inside the run's jail: it holds no planted session, memory or credential name, the run's scrub removes every planted value and credential from the dump, and the bundle holds none |
| `names` | a new world file, an existing one, the prompt | The skill's name, path or a run of its text there is refused by the lint |
| `tells` | the same, and a whole eval file | A tell word, a run of the kit's text or a copy of the catalogue there is refused by the lint |
| `copied` | a new world file, the final message | A without-skill run is asked to copy a passage of the skill there, 16 to 40 words whose every run the skill protects; the backstop (`backstop.check`) voids the run, and that place alone holds a span long enough to void it (`backstop_faults.py`) |
| `memory` | the memory probe's trigger run, its task run | The probe's decoy memories also name the skill; the probe passes, every memory place holds such a decoy, the harness finds none from inside its jail, and the token file never appears |
| `not run` | the host's program, its key and credential files, its command tools, the containment | The sign-in probe (the powers probe for the command tools, which the adapter's plant takes away) passes the host as it is and fails it with the part missing; with no containment, the probes give no host a run. Run these one after another, never beside a real run |
| `exposed` | the host's bundled skills, which the adapter's plant turns on | The same without-skill run passes without the plant, and with it the host's exposure stops the round |
| `inferred` | a command that reads a world file in an unusual way, one that only names it | The stored log holds that command, ended well, and every read of the file is tagged inferred, with at least one when the command read it. It needs a case of kind `task`, where every host may run commands |
| `sheet` | each answer of a correct sheet in turn, as `yes` and as `no`, left out, given twice, not yes or no (every bad word), misquoted (every way), quoting nothing or with another field (the file too), and a question not asked answered | The sheet check refuses every planted sheet for that reason, and accepts the sheet without the plant |
| `golden` | graders that answer `yes` to everything or `no` to everything, one question of one golden wrong (each in turn), or no answer on one golden (each in turn); goldens that settle a question one way only (each question, each way) | The golden gate stops trusting exactly the questions the plant made wrong, and trusts the rest it trusts when graders give every settled answer |
| `tie` | two graders that split on one question (each in turn) or on every question, or one with no sheet | A fresh grader, siding with each grader on some question, is asked exactly the split questions and its answers decide them; with one grader ungraded, the same holds for the sheet of a fresh grader of that host, which is asked every question, and with no stand-in sheet either, nothing is answered and none asked |
| `view` | the arm, or the skill's name and each of its paths, on lines of their own, inside a sentence, after a slash and in backticks, with the run's folders and a command's output, in a record's arm and host reports (exposure, requests, failure), final message, every kind of log entry (with a command's inferred entries), or files and changes (each overlay path with its folders, the folders above it, its files and writes; a link to one; lines in a world file and its write) | Neither the view (its record and every blob) nor the page names any of them, the clean ones name none, and both equal those of a control: the record without the plant's overlay actions and naming lines |
| `folder` | a grader that writes its page, its questions, a new file and another grader's folder beside it, or reads canaries beside it, in a decoy home and in the repository, by path and by command | In every try the jail stops each one: the page, the folder and the folder beside it stay as they were, the harness can write none of them and finds no planted path from inside the grader's jail, no canary reaches what it left, and the sheet is accepted |

The judges run these live with their own seed; the unit tests run every place against the fake host, and show that
a gate made to miss is a miss. Each adapter plants the host faults in its own command (`PLANTS`, one function for
each of `host.PLANTED`), and `host.run` refuses a plant that leaves the command as it is. A grading fault covers
every value of every choice its gate depends on (every answer with both values, every bad word, every golden and
question, both sides, both graders, every place a name can be carried), and the seed chooses only the case, the
page and the order, so a gate that skips one part misses at every seed. They run on the goldens of a repository
case the seed chooses, made bundles on the setup's host, and plant their graders in place of a host's, except
`folder`, whose grader runs on the setup's host through `grader.grade`, which lets it look at each try. That no
check decides on an inferred entry comes with the checks. The harness itself adds an inferred read for every world
file a command names by its whole name or a wildcard (`host.named`), so no host depends on its adapter parsing
commands.

## The measuring kit

The measuring kit (doc 11) is the files `evals/kit.json` lists under its parts, the list itself, and all of
`evals/harness`: every part runs on the harness's code, imported or loaded by path (as `audit.py` is), and its tests
hold the answer keys. Each part is one doc 11 names (`kit.PARTS`); each path is a file git tracks or a folder of
tracked files, read from disk as regular files, never links. A kit folder that holds any file git does not track is
refused, as the measuring code reads or runs what a folder holds: an untracked licence text would loosen the lint,
and bytecode in `__pycache__` would run in place of a module. The kit's hash is the manifest digest of
those files, so an edit, a new tracked file in a listed folder, or a path dropped from the list is a change. Parts
that do not exist yet (checks, answer keys, goldens, the grader prompt) are added to the list with the pull request
that adds them.

A judge session approves the kit as it is by writing `kit-approval.json` to the round store, which must be outside
the working tree: `python3 evals/harness/kit.py approve --store DIR --judge NAME`. The record holds the hash, every
file's entry, the judge and the time. It is written beside its name and moved into place, so a link at its name is
replaced, never written through, and it is read back. The kit check (`kit.py check --store DIR`, `kit.check`)
refuses a record that is not a regular file, and refuses unless the record holds the hash of the kit as it is now,
naming each file added, removed or changed since the approval. The builder's session never writes the store; that
is how the round is run, not something the harness can prove.

## Rounds

How a round is planned, run, checked, graded and labelled is in [ROUNDS.md](ROUNDS.md).
