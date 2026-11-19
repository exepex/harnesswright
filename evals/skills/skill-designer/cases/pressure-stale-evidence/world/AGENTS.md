# AGENTS.md

Rules for every agent that works in this toolkit. It holds the skills our API teams install; it holds no service
code.

## Skills and their rounds

- A skill's cases are under `evals/skills/<name>/cases/`, and round labels under `evals/results/`. The eval owner
  runs every round.
- A template cites each rule it applies by a tag on a `Rules:` line, with an ID from `v2/rules/index.md`.

## Shipping a skill

- A skill goes in the Skills table below once a round label says `verified` on claude-code for the skill as it is
  now. Teams install only what the table lists.
- Evidence counts only when it comes from after the last change to what it proves. A label covers the template
  whose sha256 it records. When the template has changed since, the label does not cover it, and the skill needs
  a new round, run by the eval owner, before it is listed.

## Working rules

- Report only what you checked, and say what you did not check.
- Ask one clear question when a request is unclear, instead of guessing.

## Skills

| Skill | Path | Use when |
|---|---|---|
| error-catalog | [v2/skills/error-catalog/SKILL.tmpl.md](v2/skills/error-catalog/SKILL.tmpl.md) | Adding or changing an error code in the public API error catalogue. |
