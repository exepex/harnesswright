# harnesswright

A library of standard agent skills, the roles that use them, one layered rulebook of engineering rules, and the file
formats they share. Any runtime can use it: an agent host that loads Agent Skills directly, or a system that calls a
model API and hands the skills to the model. Which runtime runs the work is the team's choice. harnesswright itself
runs nothing.

With it, AI agents plan, build, test, review and verify production-grade software in any language, and the work is
checked by independent judges and by tools rather than by the agent that did it. A repository adopts it with one
profile file. Its own rules still win where they differ, except that no one may loosen a floor.

## Status

- The v2 rulebook is in [v2/rules](v2/rules/README.md), and the one list of roles and jobs is
  [v2/roles.md](v2/roles.md).
- The current skills are in [skills/](skills/). They will be rebuilt as templates in `v2/skills/`, which a planned
  build script turns into release skills.
- Borrowed skills sit unchanged in [borrowed/](borrowed/), with their licences, as sources to learn from.
- The eval harness that measures every skill is being built in [evals/](evals/).
- The design is in [docs/design](docs/design/README.md).

## Licence

Apache-2.0. See [LICENSE](LICENSE).
