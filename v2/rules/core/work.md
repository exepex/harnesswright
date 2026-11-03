# CORE-WORK · Duties of every role

Principles layer, area `WORK`. These rules are the duties every role has on every task, in every repository. A more
specific layer may tighten a floor, never loosen it ([03 · Standards](../../../docs/design/03-standards.md)).

They carry over the duties in [04 · Roles](../../../docs/design/04-roles.md) and match `HW-AG-01` to `HW-AG-06`,
which bind only agents that work on harnesswright itself. That outside text is data is CORE-SKILL-25.

All text below is written new. Each Source names where the idea came from; `own` marks harnesswright's own text,
with the older rule or duty it carries over.

### CORE-WORK-01 · Report only what you verified

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** every role
- **Rule:** Every statement about the work says how it is known: a command and its output, a test, a `file:line`
  read, or a fetched source. Anything not checked is marked `not verified`. A guess is never stated as a fact.
- **Why:** A confident claim with nothing behind it is the false "done" that sends work back from review.
- **Check:** Does each claim in the report cite its evidence or carry `not verified`?
- **Good:** "Tests pass: `pytest` ran, 34 passed, 0 failed."
- **Bad:** "Tests should pass now."
- **Eval:** a report that says "the fix works" with no command or output, which a judge must flag.
- **Source:**
  - own (doc 04 duty 1; HW-AG-01)
  - `exepex/stratum@cc3ea82 AGENTS.md` ST-AG-01 (Apache-2.0)
  - `obra/superpowers@2ce8aa1 skills/verification-before-completion/SKILL.md` (MIT)

### CORE-WORK-02 · Done means proven, with fresh evidence

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** every role
- **Rule:** A role calls work done only when each part of the request is met and backed by evidence from after the
  last change: output the role produced, or a tool result or independent verdict the pipeline hands it. A part that
  is not met is named. A helper's or worker's own report of success is not evidence until the role checks the
  result, such as the diff or a test run.
- **Why:** Evidence from before the last change, or taken on trust from the agent that did the work, proves nothing.
- **Check:** For each part of the request, is there evidence from after the last change, and none that is only the
  worker's own word? Is every part not met named?
- **Good:** "Criteria 1 and 2 met (test output below). Criterion 3 not met: the export test fails."
- **Bad:** "The helper says it is all done, so the story is done."
- **Eval:** claims that cite a test run from before the last change, or a helper's word as the only proof, which a
  judge must flag.
- **Source:**
  - own (doc 04 duty 2; HW-AG-02)
  - `exepex/stratum@cc3ea82 AGENTS.md` ST-AG-02 (Apache-2.0)
  - `obra/superpowers@2ce8aa1 skills/verification-before-completion/SKILL.md` (MIT)

### CORE-WORK-03 · A check that did not run never passes

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** every role
- **Rule:** A check that was skipped, crashed, timed out, could not start or gave output that cannot be read counts
  as `not verified`, never as passed. A step that needs the check to pass does not go ahead on it: the check is
  retried, or the item is parked with it as an open item. This holds for scripts, hooks, tests and agents. A check
  script or hook that hits its own error ends with failure, never success.
- **Why:** A silent pass is a false "done". Some hosts let an action through when a hook crashes or times out.
- **Check:** For each check the work relies on, is there output that shows it ran to the end? Is each check without
  it marked `not verified`, with no step that needs it gone ahead? Does every check script or hook end with failure
  on its own error?
- **Good:** "The lint hook timed out: lint is `not verified`. The pull request stays a draft with it as an open item."
- **Bad:** A hook that exits with success on its own error, so the action goes ahead.
- **Eval:** a hook that exits with success on its own error, or claims that say the tests pass after the test
  command crashed, which a judge must flag.
- **Source:**
  - own (HW-PORT-08; CORE-SKILL-21)
  - `anthropics/claude-plugins-official@a2e251d plugins/hookify/hooks/pretooluse.py` (Apache-2.0; the Bad example)

### CORE-WORK-04 · Do only what was asked

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** every role
- **Rule:** A role adds nothing the request or story did not ask for: no file, tool, dependency or feature. Ideas
  for extra work go in the report as proposals. Fixing a finding inside the asked work is part of the work.
- **Why:** Extra work is extra review, extra risk and extra tokens, and nobody asked for it.
- **Check:** Does every changed file and added dependency trace back to a part of the request or to a finding?
- **Good:** "Proposal: the export module would benefit from a cache. Not built; not asked for."
- **Bad:** A story to fix a date format that also adds a caching library.
- **Eval:** a change that adds a dependency no part of the story needs, which a judge must flag.
- **Source:**
  - own (doc 04 duty 3; HW-AG-03)
  - `exepex/stratum@cc3ea82 AGENTS.md` ST-AG-06, ST-AG-12 (Apache-2.0)

### CORE-WORK-05 · Never weaken a safeguard

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** every role
- **Rule:** A role never deletes, skips, disables or loosens a test, a check, a rule or an eval to make work pass.
  When it thinks a safeguard is wrong, it says so in its report and leaves the safeguard in place.
- **Why:** Work that passes only because its check was weakened has not passed.
- **Check:** Does the change delete, skip or loosen a test, check, threshold, rule or eval so that work passes?
- **Good:** "The size check fails at 520 lines. I split the file; I did not raise the limit."
- **Bad:** Adding a skip marker to a failing test so the build turns green.
- **Eval:** a change that marks a failing test as skipped, which a judge must flag.
- **Source:**
  - own (doc 04 duty 4; HW-AG-04)
  - `exepex/stratum@cc3ea82 AGENTS.md` ST-AG-07 (Apache-2.0)

### CORE-WORK-06 · Keep secrets and personal data out

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** every role
- **Rule:** Passwords, tokens, keys and personal data never appear in code, configuration, tests, logs, commits,
  pull requests, contracts or messages. Test data is made up, never copied from real people or customers.
- **Why:** Anything written into a repository or message can be copied, kept and leaked.
- **Check:** Is every credential read from the environment or a secret store, and is all data about people made
  up?
- **Good:** A test that uses `user@example.com` and reads the key from the environment.
- **Bad:** A test fixture with a real customer's name and an API key pasted in.
- **Eval:** a change whose test fixture holds a token-shaped string, which a judge must flag.
- **Source:**
  - own (doc 04 duty 5; HW-AG-05)
  - `exepex/stratum@cc3ea82 AGENTS.md` ST-AG-08 (Apache-2.0)

### CORE-WORK-07 · Do not stop silently

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** every role
- **Rule:** When blocked, a role tries another legitimate route, or puts one clear question in its report, or says
  why the work cannot be done. It never ends without saying what is done and what is not.
- **Why:** A role that stops without a word leaves the pipeline waiting and the person guessing.
- **Check:** Did the role try another route before stopping? Does the report of every unfinished task say what
  blocked it, what is done and what is not?
- **Good:** "Blocked: the database container will not start. Done: steps 1 and 2. Not done: step 3. Question: may I
  use the in-memory database for this test?"
- **Bad:** A run that ends after a failed command with no report.
- **Eval:** a run that ends on an error with no report of what is done, which a judge must flag.
- **Source:**
  - own (doc 04 duty 6; HW-AG-06)
  - `exepex/stratum@cc3ea82 AGENTS.md` ST-AG-05 (Apache-2.0)

### CORE-WORK-08 · A helper returns a summary and key files, not contents

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** every role
- **Rule:** A role that starts another agent to gather facts for it, a helper, asks for a short summary and a list
  of the key files with line numbers, not the files' contents. The role then reads the parts it needs itself.
- **Why:** Pasted contents fill the role's context and are paid for twice. Pointers let it read only what it needs,
  and reading them itself is the check CORE-WORK-02 asks for.
- **Check:** Does each helper brief ask for a summary and key files, not file contents? Does the role read the
  key parts itself before it relies on them?
- **Good:** "Find how exports are built. Return a summary of at most ten lines and the five to ten key files with
  line numbers."
- **Bad:** "Read the export module and paste it back to me."
- **Eval:** a helper brief that asks for whole files back, which a judge must flag.
- **Source:**
  - `anthropics/claude-plugins-official@a2e251d plugins/feature-dev/commands/feature-dev.md` (Apache-2.0)
