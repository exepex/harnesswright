# AGENTS.md

Rules for every agent that works in this repository. It holds the skills our data platform team installs in the
services that own a database. It holds no service code.

## New skills

- Before anyone starts on a new skill, its request must say two things: the job the skill does, in one sentence
  that names what it produces, and the role in `v2/roles.md` whose work that is.
- When a request leaves out either one, ask the person one question that covers what is missing, and write
  nothing until they answer. Do not choose the job or the role for them.
- A skill starts with its cases under `evals/skills/<name>/cases/`. Its template under `v2/skills/<name>/` comes
  later, once its cases are reviewed and a round without the skill has run.
- A template cites each rule it applies by a tag on a `Rules:` line, with an ID from `v2/rules/index.md`.

## Working rules

- Report only what you checked, and say what you did not check.
- Agents keep their working notes under `.harness/runs/`. That folder is not part of the toolkit.

## Skills

| Skill | Path | Use when |
|---|---|---|
| query-review | [v2/skills/query-review/SKILL.tmpl.md](v2/skills/query-review/SKILL.tmpl.md) | Reviewing the SQL queries a pull request adds or changes, for missing indexes and full-table scans. |
