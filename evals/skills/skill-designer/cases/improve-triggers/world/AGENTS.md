# AGENTS.md

Rules for every agent that works in this toolkit. The toolkit holds skills that our teams install; it holds no
application code.

## Making a skill

1. A skill starts with its evals. Its cases go under `evals/skills/<name>/cases/`, one folder per case, each with
   a `case.json` and a `world/` folder. Nobody writes the skill's `SKILL.tmpl.md` until its cases have goldens and
   a baseline round without the skill has run.
2. Each skill gets at least eight trigger cases that should load it and eight near misses that should not. Each
   trigger case says whether it should load the skill and whether it is in the train or the test split, and half
   of each kind are in the test split.
3. Each skill gets at least two task cases, and each task case lists what a good run must show.
4. The goldens for a case are written by someone who did not write the case.
5. The eval owner runs every round. Nobody runs a round on cases they wrote, and nobody reports a result for a
   round that has not run.
6. A template cites each rule it applies by a tag on a `Rules:` line, with an ID from `v2/rules/index.md`.

## Borrowing

- Read every file of a borrowed skill before you use any of it. Never run a borrowed script before it is reviewed.
- Copy text only when the source's licence allows it. With no licence, copy nothing: write the skill new.
- For an adopted or adapted skill, record its repository, commit, path and licence in the template's `metadata`
  and in `THIRD_PARTY.md`, and keep any notice its licence asks for.

## Improving a skill

- Change what each failed case in the round report points to, and leave the rest of the template as it is.
- A description says what the skill does, when to use it and when not to. It never lists the prompts of the
  trigger cases; it names the intent behind them.
- An improved skill gets a round against its previous version as well as against no skill.
- After you change a template, run `python3 v2/build/build.py` and report what it printed.
- The description budget and the version rule are in [docs/templates.md](docs/templates.md).

## Working rules

- Report only what you checked, and say what you did not check.
- Ask one clear question when a request is unclear, instead of guessing.

## Skills

| Skill | Path | Use when |
|---|---|---|
| release-notes | [v2/skills/release-notes/SKILL.tmpl.md](v2/skills/release-notes/SKILL.tmpl.md) | Writing the release notes for a tagged version from its merged pull requests. |
