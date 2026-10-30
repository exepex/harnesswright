# Eval runner

Runs a skill's trigger and task evals on one host, through that host's adapter in `adapters/<host>/`. It replaces
the `claude -p` calls in Anthropic's skill-creator scripts, so the same evals run on every host.

- Python 3 standard library only. The runner makes no network calls of its own; only the host it starts does.
- Deterministic: the same eval files and host output give the same results file.
- It never decides a result by guessing. A run that fails, or a host that cannot run, is recorded as such and is
  left out of every rate.

## Commands

Run from the repository root.

```sh
# Trigger evals: each query runs --runs times in a fresh workspace with only the skill installed.
python3 evals/runner/run_evals.py triggers --skill skills/NAME --host claude-code \
  --out RESULTS/triggers.json [--runs 3] [--model MODEL] [--holdout 0.4 --seed 42] [--description TEXT]

# Task evals: each task runs in a fresh workspace; outputs, transcript and script checks are saved.
# Run once with the skill and once with --baseline (without it), into the same --out-dir.
python3 evals/runner/run_evals.py tasks --skill skills/NAME --host claude-code \
  --out-dir RESULTS/tasks [--runs 3] [--base FOLDER] [--baseline] [--model MODEL]

# After an independent grader has written grading.json next to each run: the task pass rate.
python3 evals/runner/run_evals.py score --tasks-dir RESULTS/tasks --out RESULTS/task-score.json
python3 evals/runner/run_evals.py score --tasks-dir RESULTS/tasks --configuration without_skill \
  --out RESULTS/baseline-score.json

# Labels for every host and model pairing, against the reference host.
python3 evals/runner/run_evals.py label --skill NAME --reference claude-code \
  --entry claude-code,RESULTS/triggers.json,RESULTS/task-score.json,RESULTS/baseline-score.json \
  --compatible "codex,no codex command or credential" --out evals/results/NAME.json
```

The eval files default to `evals/skills/NAME/triggers.json` and `tasks.json`; `--evals` names another file.
`--base` copies a folder into each task workspace before the task's input files. Keep it a small fixture: a copy
of this repository gives the host everything in it.
`--baseline` runs the tasks without the skill. `--description` tests a new description without editing the skill;
with `--holdout`, results are split into train and test sets, stratified by `should_trigger`, so a description is
tuned on train failures and chosen by its test score.

Without `--model`, the host uses its own default. Results record the model the host reports it used; a host that
reports none records the `--model` given, or `null`, which leaves the label `incomplete`.

## Equal powers

Every host gets the same powers in a task run: it may run commands, write only inside the workspace and a scratch
folder, and has no network. The scratch folder lives outside the workspace, is set as `XDG_CACHE_HOME` (so tools
such as `go test` can keep a cache) and is deleted after the run. The adapter records these powers as
`permission_profile`. A host that cannot give them, such as Claude Code on Linux without `bwrap`, is `not run`. A
task run in which the host refused any action fails with `host refused N action(s)`, and is never scored as a
success.

## Sealed runs

Every host run, trigger or task, with or without the skill, is sealed off from the machine that runs the evals
(`seal.py`). Unsealed, a Claude Code host started from a Claude Code session joined that session, loaded its
project memory, learned the skill's name and path, and a baseline run read the skill from the checkout. A sealed
run gets:

- an environment built from an allow list: `PATH`, locale, proxy and CA settings, and the sign-in variables the
  adapter names in `ENV_KEYS`, such as `ANTHROPIC_API_KEY` or `CODEX_API_KEY`. No other variable passes;
- a fresh, empty `HOME` and `TMPDIR`, deleted after the run, holding only copies of the adapter's
  `CREDENTIAL_FILES`, such as `~/.claude/.credentials.json`;
- on Linux with `bwrap`, a jail: system folders are read-only, the workspace, scratch and home folders are
  writable, `/tmp` is empty, and nothing else is mounted, so this repository, other runs and the operator's files
  are not there. A new user namespace keeps other processes' files out of reach through `/proc`. A host program
  installed outside the system folders, such as under `~/.nvm`, gets its install folder mounted read-only.

Where a host signs in with a file outside the home folder, pass it read-only with `--host-path PATH` (repeatable).
Without `bwrap`, a run gets the environment and home seal only. `isolation` and `host_paths` in `provenance` record
which. `tests/test_seal.py` plants copies of the skill, the repository, session and memory variables and a home
folder with memory, and checks that a sealed run reaches none of them.

## Provenance

Every results file records what produced it in `provenance`: `runner_commit` (`-dirty` when tracked files had
changed), `host_version` (`<CLI> --version`), `requested_model`, `permission_profile`, `isolation`, `host_paths`, `skill_sha256` (every file
of the skill as installed, including a `--description` override) and `evals_sha256` (the trigger file, or the
task file's folder without `triggers.json` and the results folder), and for task runs `base_sha256` (the `--base`
folder without `.git` and the results folder). `label` refuses results from different skill versions, or with- and
without-skill runs from different task files or `--base` contents.

## Results

**Trigger results** (`triggers`): `skill_name`, `host`, `model`, `description`, `runs_per_query`, `threshold`,
`status` (`run` or `not run`) and `not_run_reason`; `results[]` with `id`, `query`, `should_trigger`, `runs`,
`triggers`, `errors`, `trigger_rate`, `passed` (`null` when no run succeeded) and `split`; and `summary` with
`all`, `train` and `test`, each holding `total`, `scored`, `passed`, `not_run` and `accuracy`.

**Task runs** (`tasks`): one folder per run, `<task name>/<with_skill|without_skill>/run-<n>/`, holding
`outputs/` (the workspace after the run, without the installed skill), `transcript.jsonl` (the host's events),
`final-message.md` and `run.json` (`failure`, `returncode`, and `checks[]` with each expectation's `text`, `check`
and `passed`). Script checks run at once; `judge` expectations stay `null` until the grader writes
`grading.json` in the run folder. Each invocation first deletes earlier results for the same configuration, and
writes `status-<configuration>.json` with whether the host ran and which runs it made. Workspaces never contain
the results folder, nor a copy of the skill from `--base` (in `skills/` or a host's skills folder) other than the
one installed for this run. As a backstop to the seal, a baseline run whose host output holds the skill's
description has seen the skill and fails with `baseline saw the skill under test`. A task run that
times out is a failed run. `run.json` also holds `model` and
`refusals`; `status-<configuration>.json` holds `provenance`. Each task runs 3 times by default.

**Task score** (`score`): reads only the runs listed in the status file. `runs[]` with `passed` for each run,
and `task_pass_rate`, which stays `null` when the host did not run, or while any run failed or is not fully
graded. As in skill-creator's benchmark, it also gives `tasks` (per task: `runs`, `scored`, `passed`,
`pass_rate`), `min_runs_per_task`, and the `mean` and `stddev` of the run results, plus `model` and `provenance`.

**Labels** (`label`): for each host, the `model`, `trigger_accuracy`, `task_pass_rate`, `baseline_pass_rate`,
`lift` (with minus without the skill), the fewest runs behind any trigger query, task and baseline task,
`provenance`, `label` and `gaps`. The labels and thresholds are those of
[10 · Skills](../../docs/design/10-skills.md), checked in this order:

1. `incomplete` while a result is missing (baseline included, and any trigger query with no successful run), or
   the model behind the results is unknown or mixed.
2. `inconclusive` when any trigger query, task or baseline task has fewer than 3 successful runs.
3. `unsupported` when task pass rate or trigger accuracy is below 90%, or the task pass rate is more than 10
   points below the reference host.
4. `inconclusive` when the skill shows no lift over the baseline: the evals cannot show what it adds.
5. `verified` otherwise.

`compatible` is for a host that reads the standard but was not run.

## Tests

```sh
python3 -m unittest discover -s evals/runner/tests
```

The tests use a fake host, so they need no network and no credentials. The jail tests need `bwrap` on Linux and
are skipped elsewhere.
