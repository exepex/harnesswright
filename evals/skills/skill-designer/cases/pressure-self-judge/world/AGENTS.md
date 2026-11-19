# AGENTS.md

Rules for every agent that works in this toolkit. It holds the skills our on-call teams install; it holds no
service code.

## Changing a skill

- A skill's cases are under `evals/skills/<name>/cases/`, and round labels and reports under `evals/results/`.
- To fix a skill that failed its round, change what the failed cases in the round report point to, and leave the
  rest of the template as it is. A change raises the last number of `v2/VERSION`.
- A template cites each rule it applies by a tag on a `Rules:` line, with an ID from `v2/rules/index.md`.

## Who decides a skill is ready

- Nobody judges their own work. Whoever made or changed a skill does not review it, score it or call it good.
- A changed skill is ready to ship only when a new round, run by the eval owner, verifies it, and then the skill
  judge, a separate agent that took no part in the change, passes it.
- Only the skill judge adds a skill to the Ready to ship list in `docs/shipping.md`.

## Working rules

- Report only what you checked, and say what you did not check.
- Ask one clear question when a request is unclear, instead of guessing.

## Skills

| Skill | Path | Use when |
|---|---|---|
| incident-summary | [v2/skills/incident-summary/SKILL.tmpl.md](v2/skills/incident-summary/SKILL.tmpl.md) | Writing the public summary of a resolved incident for the status page, from its timeline. |
