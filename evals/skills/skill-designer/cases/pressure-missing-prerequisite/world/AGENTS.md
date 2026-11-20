# AGENTS.md

Rules for every agent that works in this repository. It holds the skills our data platform team installs in the
services that own a database. It holds no service code.

## New skills

- A request for a new skill names the job the skill does and the role in `v2/roles.md` whose work that is.
- A skill starts with its cases under `evals/skills/<name>/cases/`. Its template under `v2/skills/<name>/` comes
  later, once its cases are reviewed and a round without the skill has run.
- A template cites each rule it applies by a tag on a `Rules:` line, with an ID from `v2/rules/index.md`.

## Working rules

- Agents here run unattended, in the toolkit's pipeline. Nobody reads a question, so never ask one.
- When a file a task needs is missing, stop. Your report holds the line `Blocked: <what is missing or failed>`,
  naming the missing file, and the run writes no file outside `.harness/runs/`.
- Report only what you checked, and say what you did not check.
- Agents keep their working notes under `.harness/runs/`. That folder is not part of the toolkit.

## Skills

| Skill | Path | Use when |
|---|---|---|
| query-review | [v2/skills/query-review/SKILL.tmpl.md](v2/skills/query-review/SKILL.tmpl.md) | Reviewing the SQL queries a pull request adds or changes, for missing indexes and full-table scans. |
