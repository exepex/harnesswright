# Eval harness

The ground-up eval harness of [11 · Evals](../../docs/design/11-evals.md). It replaces the phase 2 runner in
`evals/runner/`, which stays until rounds move here (build step 5).

The harness is built in small pull requests, one part each. This folder holds the first parts: **the manifest,
eval cases, skill reading, building and proving the two arms, the world lint, containment, the network gate,
the power table, the host contract, with a fake host, and the first four probes**. The memory and drift probes,
evidence, and the measuring kit come next.

Python 3 standard library only, and no network calls of its own (`HW-PORT-04`): the gate only passes on a host's
allowed connections.

## Parts

| File | Does |
|---|---|
| `manifest.py` | The one description of a folder: every path with its kind (folder, file, link), mode and hash |
| `cases.py` | Reads `evals/skills/NAME/cases/<case>/case.json` and checks it against one schema |
| `skills.py` | Reads a skill folder and its frontmatter, and checks that a folder holds only allowed entries |
| `world.py` | Plans and builds both arms of a case, and proves each is exactly what the case says |
| `lint.py` | Rejects a case whose world or prompt is unsound, from one list of what the run can see |
| `contain.py` | Builds one run's environment, home and jail from one list of mounts |
| `audit.py` | Runs inside the jail before the host starts and checks it against the same list |
| `gate.py` | The jail's one way out: a proxy that passes on only the host's model hosts |
| `powers.py` | The power table of each mode, and the probe that proves the jail gives exactly that |
| `host.py` | The one contract between the harness and a host's adapter, and the one place a host runs |
| `probes.py` | The probes each host passes before real runs: sign-in, powers, discovery and instructions |

## Commands

Run from the repository root.

```sh
# Unit tests. The jail tests need Linux and bubblewrap (`apt-get install bubblewrap`); without them they are
# skipped and say why.
python3 -m unittest discover -s evals/harness/tests
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
- a copy names a source outside `skills/` and `evals/` and its 64-character sha256;
- an index row may use only `{name}`, `{path}` and `{description}`, with no index, attribute or format spec;
- an expectation is a text, or an object holding only a text;
- a tool is a command name;
- siblings are distinct skill names, never paths and never the skill under test;
- `allow_words` keys are world paths, `<prompt>` or `<commit N>` for a declared commit.

## How a skill is read

`skills.py` works from three rules, each a list of what is allowed.

`skills.frontmatter` reads one stated subset of YAML, with only the fields of `HW-PORT-01`: `name`, `description`,
`license` and `compatibility` hold one plain line, and `metadata` holds `  key: value` lines whose keys are
lower-case words joined by `-` and whose values are plain lines. A plain line is words separated by single spaces,
which YAML reads as exactly the text written. There are no quoted values, block scalars or comments, and a value or
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
  `evals/` but `evals/harness/` and `evals/runner/`, the general machinery, which says nothing about a skill. A new
  kit part counts without being listed. `evals/fixtures/` and a skill's `files/`, `upstream/` and
  `cases/CASE/world/` folders hold project text and are left out. Python is read for its strings, f-string text
  and comments only, since its code is the same in any Python program. So a check copied with its strings and
  comments removed is not caught here; the judge who reads the world is the check for that.
- Case data (`case.json`, `tasks.json`, `triggers.json`, and the case's own `case.json` wherever it lives) may
  repeat what the run sees of the case outside its world (its prompt, commits and index row) and its world's paths.
  Other eval text may not.
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
`powers.TOOLS`. `host.run` is the one place a host runs: in the run's jail, after the audit and inside the gate.

It checks what comes back against two allow lists. The action log may hold only the entries of `host.ENTRIES`:
reads, writes with content hashes, commands with exit code and output cut to `host.OUTPUT_LIMIT`, actions refused
by the host or the jail (`blocked`, with the reason), skill loads, sub-agents and messages, each tagged `observed`
(the host reported it) or `inferred` (the adapter worked it out, such as a file a shell command reads). The host
may expose and load only the skills the arm installs, and expose only the adapter's tools. A host that ran must
report what it exposed: no report is never read as "nothing". Anything else raises `HostError`, and the round
stops. The jail's audit runs first, and a host that crashes or times out is a `failure`: the run is void.

`tests/fakehost/` is a fake host and its adapter: a program with no model that carries out a list of actions, with
its own sandbox, a bundled skill and a tool beyond the table, as a real host has. The tests run it in a real jail,
so the contract and its faults are shown end to end in every pull request. The Codex and Claude Code adapters give
the contract too ([adapters](../../adapters/README.md#the-harness-contract)), beside the older interface that
`evals/runner/` still uses.

An adapter reports a write that failed as `failed`, and `host.run` decides what it was from the jail's own mount
list: when the nearest mount above the path is not writable, the jail refused it and it is `blocked`; otherwise it
is left out, as the world diff shows. Paths inside the world are logged relative to it, on every host. An
adapter's `RUN_ENV` holds fixed variables it sets for every run; they are never taken from the operator.

## Probes

A probe is a probe world, a prompt and a check of the files the host left in the probe-output folder, never of
what the model says (doc 11, Probes). `probes.probe(adapter, name, mode, root)` runs one probe through `host.run`,
in a containment made with `probe=True`, and returns why it failed, or `None`; `probes.probe_host` runs every probe
in both modes and returns the reasons the host is `not run`. The probe-output folder is the one place a probe run
may write beyond the table, in both modes; real runs never have it, and `powers.spec` adds it to the places the
powers probe allows only when it is there.

- **Sign-in:** the host writes `ready` into `sign-in.txt`.
- **Powers:** the host runs `powers.PROBE` itself, with the spec the harness put in the folder, and its output is
  checked against the table with `powers.check`, so its own commands are shown to get the jail's powers.
- **Discovery:** asked for the probe skill by name, with up to two tries, the host writes the token that only the
  skill's `SKILL.md` holds.
- **Instructions:** the host writes back the tokens its instructions give it. The probe world has an `AGENTS.md`
  with one token and a `CLAUDE.md` that imports it, so every host must report exactly that one token, and a host
  that searched the world would also find the skill's.

Every token is fresh for each run. A host or containment that breaks its contract raises, as in any run.
