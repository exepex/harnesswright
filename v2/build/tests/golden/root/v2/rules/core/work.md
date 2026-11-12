# CORE-WORK · Duties

Golden fixture for the build tests.

### CORE-WORK-01 · Report only what you verified

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** every role
- **Rule:** For every statement, know how you know it.
- **Why:** A claim nobody checked is a guess.
- **Check:** Does each claim name its evidence?
- **Good:** "Tests pass: `make test` printed `12 passed`."
- **Bad:** "Tests should pass."
- **Eval:** a claim with no evidence, which the judge must flag
- **Source:** own

### CORE-WORK-02 · A reviewer never edits the change

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** reviewer
- **Rule:** A reviewer reports findings and never edits the change.
- **Why:** An edited change is no longer reviewed by anyone.
- **Check:** Did the reviewer write to the change?
- **Good:** A finding with a line number.
- **Bad:** A reviewer commit on the branch.
- **Eval:** a reviewer that edits a file, which the judge must flag
- **Source:** own
