# AGENTS.md

Rules for agents in the library loans service.

## When a criterion is met

- A criterion is met only when, for each test type its story lists, a test of that type exercises the criterion and
  passes.
- A suite that passes proves nothing about a criterion no test exercises. Report such a criterion as not met or not
  proven, never as met.
- Writing the claims changes no code and no tests. A criterion with no test is reported as it stands, not fixed.
