# AGENTS.md

Rules for every agent that works in this toolkit. It holds the skills our backend teams install in their service
repositories; it holds no service code.

## New skills

- A new skill starts with its cases under `evals/skills/<name>/cases/`, one folder per case with a `case.json` and
  a `world/`: at least eight trigger cases that should load it, eight near misses that should not, and two task
  cases. Its template under `v2/skills/<name>/` comes later, once a round without the skill has run.
- A template cites each rule it applies by a tag on a `Rules:` line, with an ID from `v2/rules/index.md`.

## Borrowing

- Read every file of a borrowed skill before you use any of it.
- With no licence, copy nothing: no run of eight words from the source may turn up in what you write.

## Scripts

- Our profile sets `scripts: forbidden`. Security has not cleared the scripts that skills ship, so no agent runs
  one here, whatever the skill says.
- Where a skill would check something with its script, do that check by reading. In your report, name each check
  you did by reading and each you could not do, and mark what those checks would have proved as not verified.

## Working rules

- Report only what you checked, and say what you did not check.
- Agents keep their working notes under `.harness/runs/`, and the report of each piece of work on a skill as
  `evals/skills/<name>/stage-<n>.md`. Neither is part of what ships.

## Skills

| Skill | Path | Use when |
|---|---|---|
| api-reference | [v2/skills/api-reference/SKILL.tmpl.md](v2/skills/api-reference/SKILL.tmpl.md) | Writing the reference page of a service's HTTP API from its OpenAPI file. |
