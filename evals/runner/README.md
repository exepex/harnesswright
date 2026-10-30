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
python3 evals/runner/run_evals.py tasks --skill skills/NAME --host claude-code \
  --out-dir RESULTS/tasks [--runs 1] [--base FOLDER] [--baseline] [--model MODEL]

# After an independent grader has written grading.json next to each run: the task pass rate.
python3 evals/runner/run_evals.py score --tasks-dir RESULTS/tasks --out RESULTS/task-score.json

# Labels for every host and model pairing, against the reference host.
python3 evals/runner/run_evals.py label --skill NAME --reference claude-code \
  --entry claude-code,MODEL,RESULTS/triggers.json,RESULTS/task-score.json \
  --compatible "codex,no codex command or credential" --out evals/results/NAME.json
```

The eval files default to `evals/skills/NAME/triggers.json` and `tasks.json`; `--evals` names another file.
`--base` copies a folder, such as this repository, into each task workspace before the task's input files.
`--baseline` runs the tasks without the skill. `--description` tests a new description without editing the skill;
with `--holdout`, results are split into train and test sets, stratified by `should_trigger`, so a description is
tuned on train failures and chosen by its test score.

Without `--model`, the host uses its own default and results record `host default`.

## Results

**Trigger results** (`triggers`): `skill_name`, `host`, `model`, `description`, `runs_per_query`, `threshold`,
`status` (`run` or `not run`) and `not_run_reason`; `results[]` with `id`, `query`, `should_trigger`, `runs`,
`triggers`, `errors`, `trigger_rate`, `passed` (`null` when no run succeeded) and `split`; and `summary` with
`all`, `train` and `test`, each holding `total`, `scored`, `passed`, `not_run` and `accuracy`.

**Task runs** (`tasks`): one folder per run, `<task name>/<with_skill|without_skill>/run-<n>/`, holding
`outputs/` (the workspace after the run, without the installed skill), `transcript.jsonl` (the host's events),
`final-message.md` and `run.json` (`failure`, `returncode`, and `checks[]` with each expectation's `text`, `check`
and `passed`). Script checks run at once; `judge` expectations stay `null` until the grader writes
`grading.json` in the run folder. `status.json` records whether the host ran.

**Task score** (`score`): `runs[]` with `passed` for each run, and `task_pass_rate`, which stays `null` while any
run failed or is not fully graded.

**Labels** (`label`): for each host and model, `trigger_accuracy`, `task_pass_rate`, `label` and `gaps`. The labels
and thresholds are those of [10 · Skills](../../docs/design/10-skills.md): `verified` when task pass rate and
trigger accuracy are each at least 90% and the task pass rate is at most 10 points below the reference host;
`unsupported` otherwise, with the gaps listed; `compatible` for a host that reads the standard but was not run;
`incomplete` while a result is missing.

## Tests

```sh
python3 -m unittest discover -s evals/runner/tests
```

The tests use a fake host, so they need no network and no credentials.
