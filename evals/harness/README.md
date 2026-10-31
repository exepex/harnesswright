# Eval harness

The ground-up eval harness of [11 · Evals](../../docs/design/11-evals.md). It replaces the phase 2 runner in
`evals/runner/`, which stays until rounds move here (build step 5). This folder holds build step 2: worlds,
containment and probes. Checks and cases (step 3), grading (step 4) and rounds (step 5) come next.

Python 3 standard library only, and no network calls of its own (`HW-PORT-04`).

## Parts

| File | Does |
|---|---|
| `cases.py` | Reads and checks `evals/skills/NAME/cases/<case>/case.json`; hashes file trees |
| `world.py` | Builds both arms of a case from its world, and proves they differ only by the skill |
| `lint.py` | The world lint: skill name, path or own text, eval files, test tells, `.git`, outside symlinks, drifted copies |
| `contain.py` | Each run's folders, allow-listed environment and `bwrap` jail; canaries |
| `audit.py` | The visibility audit, run inside the jail before the host starts |
| `powers.py` | The power table for each mode, and the probe script that measures it |
| `hostrun.py` | Runs a host once: audit, host, action log |
| `evidence.py` | The action log format, world diff, bundles with redaction, and the grader view |
| `probes.py` | The six probes for one host and mode |
| `kit.py` | The measuring kit's hash, and the check that judges approved it |
| `hosts.py` | Loads `adapters/<host>/adapter.py` |

The fault catalogue is `evals/faults/harness.json`. Each harness fault names the unit test that plants it.

## Commands

Run from the repository root.

```sh
# Probes for one host and mode. Exit code 1 when any probe fails; the report says why.
python3 evals/harness/probes.py --host codex --mode task --out PROBES [--tool go] [--model MODEL]

# The world lint of every case of a skill, for one host.
python3 evals/harness/lint.py --skill NAME --host codex

# The measuring kit: its hash, its files, and whether judges approved it.
python3 evals/harness/kit.py hash
python3 evals/harness/kit.py check --store STORE

# Unit tests, including every harness fault against the fake host. They need bwrap.
python3 -m unittest discover -s evals/harness/tests
```

## How a run is contained

`contain.Containment` gives each run a fresh private home (only copies of the adapter's credential files), a
scratch folder in task runs (which holds `TMPDIR` and the cache), and an environment built from an allow list.
In the `bwrap` jail, system folders are read-only, `/etc/codex` and `/etc/claude-code` are empty, `/tmp` is empty,
and the world is read-only in trigger runs. Before the host starts, `audit.py` runs in the same jail and fails on
any variable outside the allow list, any entry of `/` or of a folder above a mount that is not the way to a mount,
a readable forbidden path or planted canary, a masked folder that is not empty, or a world whose hash is not the
built arm's. A failed audit raises `ContainmentError`: the run is voided and the round stops.

Each adapter configures its host to the power table: Codex with `skills.bundled.enabled=false`, its extras turned
off and `/tmp` left out of the writable roots; Claude Code with only the table's tools, bundled skills and built-in
plugins off and every command in its sandbox. Host skills that cannot be turned off are listed in the adapter as
`HOST_SKILLS` and approved with the kit.

## The fake host

`tests/fakehost/` is a host without a model. It loads instruction files and any memory in its home, finds skills,
runs commands in its own sandbox and reports every action. The tests install it outside the repository and plant
each harness fault against it: a negative control shows each fault is caught when the containment is broken.

## Evidence

- Codex 0.166.0, live on 2026-10-31 in this container with `bwrap` 0.9.0 and `socat` installed: all six probes
  passed in both modes. Trigger powers measured: reads of world and system only, no write anywhere, no network.
  Task powers measured: writes to world, scratch and temp only; home, `/tmp` and system folders refused; no
  network. Its self-writes in an empty run are files under `.codex/` in the private home and nothing in the world.
- Codex 0.166.0 in a fresh home installs five bundled skills (`skill-creator`, `skill-installer`, `imagegen`,
  `openai-docs`, `review-agent`) and syncs a plugin repository; `skills.bundled.enabled=false` and
  `--disable plugins` stop both. A command its execution policy refuses appears only on stderr ("rejected: policy
  forbids commands starting with ..."), never in the JSON events, so the adapter reads refusals from stderr.
- Claude Code 2.1.316 in a fresh home lists 18 bundled skills and three built-in plugins.
  `CLAUDE_CODE_DISABLE_BUNDLED_SKILLS=1` with `disableBundledSkills` and the plugins turned off in the settings
  leaves `design` and `doctor`, the adapter's `HOST_SKILLS`.
- Claude Code was not probed live: this container has no Claude Code sign-in a sealed run may use, so its sign-in
  probe fails ("Not logged in") and the host is `not run`. Its powers in this configuration are not verified yet.
- Unit tests: `python3 -m unittest discover -s evals/harness/tests` runs 41 tests, all passing.
