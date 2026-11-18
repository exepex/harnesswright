# AGENTS.md

Rules for every agent that works in this toolkit. The toolkit holds skills that our teams install; it holds no
application code.

## Making a skill

A skill starts with its evals. How its cases are laid out, the order of the work and who does each part are in
[docs/evals.md](docs/evals.md). A template cites each rule it applies by a tag on a `Rules:` line, with an ID from
`v2/rules/index.md`, and never copies the rule's words.

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
| pr-summary | [v2/skills/pr-summary/SKILL.tmpl.md](v2/skills/pr-summary/SKILL.tmpl.md) | Writing or updating the description of an open pull request from its diff. |
| release-notes | [v2/skills/release-notes/SKILL.tmpl.md](v2/skills/release-notes/SKILL.tmpl.md) | Writing the release notes for a tagged version from its merged pull requests. |
