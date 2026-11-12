---
name: golden-skill
description: Golden fixture for the build tests. Never used as a real skill.
metadata:
  roles: tester
  areas: rest
  copied-ids: "CORE-WORK-01, CORE-DP-NAMES, CORE-TEST-01, CORE-TEST-011"
  rulebook-version: "0.3.1"
  content-hash: "d5adbdc30ebce50d0a010bd8295f2a2c52f4beae7188895ed197b7eaac2c78fa"
  size-floors: "284"
  size-rest: "1703"
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

1. Keep each test to one behaviour, as CORE-TEST-011 (A test checks one behaviour) says.
2. Name tests in the style CORE-DP-NAMES (How tests are named) binds.
3. See [the guide](references/guide.md); the file `CORE-TEST-01.md` is a name, not a citation.
