# Entry format

- One line per pull request, under its section of `## Unreleased`. The sections keep the order Added, Changed,
  Fixed, and an empty section is left out.
- Past tense, about twenty words at most, and no ticket jargon a user would not know.
- On a long branch, hand the commit list to a sub-agent through the Task tool and ask it for one line per commit;
  then pick the commit that says what a user notices.
- When `CLAUDECODE` is set, the changelog is already open in the editor pane: edit it there rather than writing
  the whole file again.
