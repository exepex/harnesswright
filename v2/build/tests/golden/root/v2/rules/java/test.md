# JAVA-TEST · Tests in Java

Golden fixture. The build reads only the CORE layer, so this rule must never reach a release skill.

### JAVA-TEST-01 · Use AssertJ

- **Kind:** idiom
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** every role
- **Rule:** Assert with AssertJ.
- **Why:** One assertion style.
- **Check:** Are assertions AssertJ?
- **Good:** `assertThat(x).isEqualTo(1)`
- **Bad:** `assertEquals(1, x)`
- **Eval:** a JUnit assertion, which the reviewer must flag
- **Source:** own
