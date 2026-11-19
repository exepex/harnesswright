# AGENTS.md

Rules for agents in the parking fees service.

## Finishing a story

- When a story is finished, its claims go in the run folder, as `claims/<story>.md` next to `stories/`.
- No agent reviews, judges or approves a change it worked on. Writing the claims for a change counts as working on it.
- The story judge decides whether a story passes: a separate agent that reads only the story, the claims and the
  diff. A change is merged only after the story judge passes it.
