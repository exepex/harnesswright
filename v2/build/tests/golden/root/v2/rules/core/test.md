# CORE-TEST · Tests

Golden fixture for the build tests. These rules are not part of the real rulebook.

### CORE-TEST-01 · A test names its scenario

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** tester
- **Rule:** Name each test after the situation it sets up
  and the result it expects.
- **Why:** A failing test should say what broke.
- **Check:** Can I tell from the name what failed?
- **Good:**
  ```java
  void rejectsOrderWhenStockIsLow() {}

  void acceptsOrderWhenStockIsEnough() {}
  ```
- **Bad:** `testOrder2`
- **Eval:** a test named `testOrder2`, which the reviewer must flag
- **Exceptions:** generated tests,
  and tests copied unchanged from a vendor.
- **Source:**
  - own
    - first written for the golden release
  - `a/b@1234567 c.md` (MIT)

### CORE-TEST-011 · A test checks one behaviour

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** reviewer
- **Rule:** Each test checks one behaviour.
- **Why:** Two behaviours in one test hide which one broke.
- **Check:** Does the test assert one outcome?
- **Good:** One test for the low-stock case, one for the enough-stock case.
- **Bad:** One test that asserts both cases.
- **Eval:** a test with two unrelated assertions, which the reviewer must flag
- **Source:** own

### CORE-TEST-02 · A test runs in under a second

- **Kind:** principle
- **Status:** inferred
- **Review by:** 2027-11-03
- **Applies to:** every role
- **Rule:** Each unit test runs in under a second.
- **Why:** Slow tests are skipped.
- **Check:** Time the suite.
- **Good:** A 20 ms test.
- **Bad:** A 3 s test.
- **Eval:** a 3 s unit test, which the reviewer must flag
- **Source:** own

### CORE-TEST-04 · A test checks one outcome per case

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** reviewer
- **Overrides:** CORE-TEST-011
- **Rule:** Each test case checks one outcome; a table of cases may share one test.
- **Why:** Table tests keep many small cases readable.
- **Check:** Does each case assert one outcome?
- **Good:** One table test with a low-stock row and an enough-stock row.
- **Bad:** One case that asserts two outcomes.
- **Eval:** a case with two unrelated assertions, which the reviewer must flag
- **Source:** own
