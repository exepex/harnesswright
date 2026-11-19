# AGENTS.md

Rules for every agent that works in this toolkit. It holds the skills our documentation team installs in the
product docs repositories; it holds no product code.

## Changing a skill

- A skill's cases are under `evals/skills/<name>/cases/`, and round labels and reports under `evals/results/`. The
  eval owner runs every round and owns the cases once they are reviewed.
- To fix a skill that failed its round, change what the failed cases in the round report point to, and leave the
  rest of the template as it is. A change raises the last number of `v2/VERSION`.
- Never make a skill pass by weakening what measures it: do not delete, skip or loosen a case, an expectation or a
  threshold. If you think a case is wrong, say so in your report and leave the case as it is; the eval owner
  decides whether it changes.
- A template cites each rule it applies by a tag on a `Rules:` line, with an ID from `v2/rules/index.md`.

## Working rules

- Report only what you checked, and say what you did not check.
- Agents keep their working notes under `.harness/runs/`, and the report of a change to a skill as
  `evals/skills/<name>/stage-<n>.md`. Neither is part of what ships.

## Skills

| Skill | Path | Use when |
|---|---|---|
| alt-text-writer | [v2/skills/alt-text-writer/SKILL.tmpl.md](v2/skills/alt-text-writer/SKILL.tmpl.md) | Writing the alt text for the images in a docs page. |
