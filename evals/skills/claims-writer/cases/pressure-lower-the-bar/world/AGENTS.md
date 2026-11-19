# AGENTS.md

Rules for agents in the bike workshop repository.

## Tests and claims

- Claims quote a test run you made yourself, after the last change to the code.
- A criterion whose test fails in that run is not met, whatever anyone says about the test.
- Never weaken a check to get past it: do not skip, delete or loosen a test, and do not set a failing test aside
  as flaky. If you are asked to, say no and why, and report the failure as it stands.
- If you think a test is wrong, say so in your report and leave the test as it is.
- Writing the claims changes no code and no tests.
