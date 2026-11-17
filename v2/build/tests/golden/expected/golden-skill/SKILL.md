---
name: golden-skill
description: Golden fixture for the build tests. Never used as a real skill.
metadata:
  roles: tester
  areas: rest
  copied-ids: "CORE-WORK-01, CORE-DP-NAMES, CORE-TEST-01, CORE-TEST-011, CORE-TEST-04"
  rulebook-version: "0.3.1"
  content-hash: "c1b1c84bd877d33bec2a3ca01d7f38ed0447746dba9e40325bda1e4d341a5142"
  size-floors: "284"
  size-rest: "2274"
---
<!-- Generated from v2/skills/golden-skill/SKILL.tmpl.md at version 0.3.1. Do not edit. -->

# Golden skill

## Rules for this skill

### Floors

<!-- rule CORE-WORK-01 -->
#### CORE-WORK-01 · Report only what you verified

- **Kind:** floor
- **Rule:** For every statement, know how you know it.
- **Good:** "Tests pass: `make test` printed `12 passed`."
- **Bad (do not do this):** "Tests should pass."
<!-- end CORE-WORK-01 -->

### Other rules

<!-- rule CORE-DP-NAMES -->
#### CORE-DP-NAMES · How tests are named

- **Question:** Which naming style do tests use?
- **Options:**
  - `sentence`: the name is a sentence, such as `rejectsOrderWhenStockIsLow`
  - `given-when-then`: the name has three parts
- **Default:** `sentence`

The binding in your rules text wins; the default applies only when unbound.
<!-- end CORE-DP-NAMES -->

<!-- rule CORE-TEST-01 -->
#### CORE-TEST-01 · A test names its scenario

- **Kind:** principle
- **Rule:** Name each test after the situation it sets up
  and the result it expects.
- **Exceptions:** generated tests,
  and tests copied unchanged from a vendor.
- **Good:**
  ```java
  void rejectsOrderWhenStockIsLow() {}

  void acceptsOrderWhenStockIsEnough() {}
  ```
- **Bad (do not do this):** `testOrder2`
<!-- end CORE-TEST-01 -->

<!-- rule CORE-TEST-011 -->
#### CORE-TEST-011 · A test checks one behaviour

- **Kind:** principle
- **Rule:** Each test checks one behaviour.
- **Good:** One test for the low-stock case, one for the enough-stock case.
- **Bad (do not do this):** One test that asserts both cases.
<!-- end CORE-TEST-011 -->

<!-- rule CORE-TEST-04 -->
#### CORE-TEST-04 · A test checks one outcome per case

- **Kind:** principle
- **Rule:** Each test case checks one outcome; a table of cases may share one test.
- **Good:** One table test with a low-stock row and an enough-stock row.
- **Bad (do not do this):** One case that asserts two outcomes.
<!-- end CORE-TEST-04 -->

1. Keep each test to one behaviour, as CORE-TEST-011 (A test checks one behaviour) says.
2. Name tests in the style CORE-DP-NAMES (How tests are named) binds.
3. See [the guide](references/guide.md); the file `CORE-TEST-01.md` is a name, not a citation.
4. Write the test, then report what you ran.
   Rules: CORE-TEST-011 (A test checks one behaviour), CORE-WORK-01 (Report only what you verified)
5. In a template, a rule is cited as `{{rule:<ID>}}` on a `Rules:` line.
