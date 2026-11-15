# AGENTS.md

Rules for every agent that works in this toolkit. The toolkit holds skills that our teams install; it holds no
application code.

## Making a skill

1. A skill starts with its evals. Before anyone writes `v2/skills/<name>/SKILL.tmpl.md`, its cases exist under
   `evals/skills/<name>/cases/`, one folder per case, each with a `case.json` and a `world/` folder.
2. Each skill gets at least eight trigger cases that should load it and eight near misses that should not.
3. Each skill gets at least two task cases, and each task case lists what a good run must show.
4. The goldens for a case are written by someone who did not write the case.
5. The eval owner runs every round. Nobody runs a round on cases they wrote, and nobody reports a result for a
   round that has not run.
6. A template cites the rules it applies by the IDs in `v2/rules/index.md` and never copies their text.

## Borrowing

- Read every file of a borrowed skill before you use any of it. Never run a borrowed script before it is reviewed.
- Copy text only when the source's licence allows it. With no licence, copy nothing: write the skill new.
- For an adopted or adapted skill, record its repository, commit, path and licence in the template's `metadata`
  and in `THIRD_PARTY.md`, and keep any notice its licence asks for.

## Working rules

- Report only what you checked, and say what you did not check.
- Ask one clear question when a request is unclear, instead of guessing.

## Skills

| Skill | Path | Use when |
|---|---|---|
| release-notes | [v2/skills/release-notes/SKILL.tmpl.md](v2/skills/release-notes/SKILL.tmpl.md) | Writing the release notes for a tagged version from its merged pull requests. |
