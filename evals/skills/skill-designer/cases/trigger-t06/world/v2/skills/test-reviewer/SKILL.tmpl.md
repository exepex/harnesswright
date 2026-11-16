---
name: test-reviewer
description: Review the tests of a change.
---

# Test reviewer

Tests matter a great deal, and a good reviewer keeps many things in mind at once: naming, coverage,
speed, flakiness, readability and the habits of the team that owns the code.

1. Look over the tests and get a feel for them.
2. Think about whether anything important might be missing, in the broadest sense.
3. Consider naming. Names should be clear. Some teams prefer given-when-then, others prefer
   should-style names, and some like plain sentences; any of these can be fine if used the same way.
4. Make sure the tests are good.
5. Look at speed. Slow tests are a problem, though some slowness is fine for integration tests,
   and the line between the two depends on the project, the build and the people who run it.
6. Write up your thoughts.
