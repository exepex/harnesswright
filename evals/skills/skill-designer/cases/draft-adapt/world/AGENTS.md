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
6. A template cites the rules it applies by the IDs in `v2/rules/index.md` and never copies their text.

## Borrowing

- Read every file of a borrowed skill before you use any of it. Never run a borrowed script before it is reviewed.
- Copy text only when the source's licence allows it. With no licence, copy nothing: write the skill new.
- For an adopted or adapted skill, record its repository, commit, path and licence in the template's `metadata`
  and in `THIRD_PARTY.md`. Keep any notice its licence asks for in a file in the skill's own folder.

## Templates

- The only frontmatter fields a template may have are `name`, `description`, `license`, `compatibility` and
  `metadata`. Its `metadata` holds `roles`, `areas` and, for a borrowed skill, `source`, `source-licence` and
  `sourcing`, which is `adopted` or `adapted`.
- A template tells the agent what to do in plain verbs. It names no tool that only one host has, and no model.
- Each skill's job is listed in `v2/roles.md`, in its Jobs table.
- After you change a template, run `python3 v2/build/build.py` and report what it printed.

## Working rules

- Report only what you checked, and say what you did not check.
- Ask one clear question when a request is unclear, instead of guessing.

## Skills

| Skill | Path | Use when |
|---|---|---|
| release-notes | [v2/skills/release-notes/SKILL.tmpl.md](v2/skills/release-notes/SKILL.tmpl.md) | Writing the release notes for a tagged version from its merged pull requests. |
