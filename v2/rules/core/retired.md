# Retired rules · Principles layer

Retired rules keep their ID and full text here for history (HW-RULE-07). They are never read by the resolver and
never given to agents. Each names the rule that replaced it.

### CORE-SKILL-02 · The frontmatter uses only standard fields, within their limits

- **Kind:** floor
- **Status:** retired
- **Replaced by:** CORE-TEMPLATE-03
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** The frontmatter holds only `name`, `description` and optionally `license`, `compatibility` and `metadata`
  (string values only). `name` matches the folder name and has at most 64 lowercase letters, digits and single
  hyphens. `description` has at most 1024 characters and no `<` or `>`. `compatibility` has at most 500 characters.
  Host-specific fields, including `allowed-tools`, live in adapters.
- **Why:** Hosts reject or treat differently anything outside the Agent Skills specification.
- **Check:** Run the frontmatter check script, or read the frontmatter against this list.
- **Good:** `name: claims-writer` in folder `skills/claims-writer/`.
- **Bad:** `name: Claims Writer` with an `allowed-tools` field in folder `skills/claims/`.
- **Eval:** a skill whose `name` has capitals and does not match its folder, which the skill judge must flag.
- **Source:**
  - `anthropics/skills@ca45fc4 skills/skill-creator/scripts/quick_validate.py` (Apache-2.0)
  - `obra/superpowers@2ce8aa1 skills/writing-skills/SKILL.md` (MIT)
  - own (HW-PORT-01)

### CORE-SKILL-04 · A skill states its purpose, limits and inputs

- **Kind:** principle
- **Status:** retired
- **Replaced by:** CORE-SKILL-28
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** The body opens with what the skill does, what it does not do, what inputs it needs, and what to do when an
  input is missing.
- **Why:** An agent missing an input guesses it. A guessed input gives a confident wrong result.
- **Check:** For each input, does the skill say where it comes from and what happens without it?
- **Good:** "Needs the story file. If there is none, stop and ask for it."
- **Bad:** A skill that uses "the acceptance criteria" without saying where they are.
- **Eval:** a skill that uses an input without saying where it comes from, which the skill judge must flag.
- **Source:**
  - own (doc 10 checklist items 1 and 3)

### CORE-SKILL-06 · A skill cites the rules it applies by ID

- **Kind:** floor
- **Status:** retired
- **Replaced by:** CORE-TEMPLATE-01, CORE-TEMPLATE-04
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** A skill tells the agent to apply the resolved rules whose Applies to names its role. It cites a rule ID
  only where one step depends on that rule. It never writes a rule's text (HW-RULE-01).
- **Why:** A copied rule goes stale when the rule changes, and the agent then sees two versions.
- **Check:** Is every sentence that says how work must be done in general either a cited ID or a step?
- **Good:** "4. Name each test as CORE-TEST-03 asks."
- **Bad:** "4. Test names must state the scenario and the expected outcome."
- **Eval:** a skill that restates a rule without its ID, which the skill judge must flag.
- **Source:**
  - `exepex/stratum@cc3ea82 AGENTS.md` ST-AG-18 (Apache-2.0)
  - own (doc 10 checklist item 5)

### CORE-SKILL-08 · A skill says what to do when a step fails

- **Kind:** principle
- **Status:** retired
- **Replaced by:** CORE-SKILL-29
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** For each step that can fail, the skill says what to do: retry, use another route, or stop and ask one
  clear question. It never lets the agent skip the step silently.
- **Why:** Without a stated path, an agent skips the failed step and reports success.
- **Check:** For each step that can fail, is there a stated next action?
- **Good:** "If the test command is not found, stop and ask which command runs the tests."
- **Bad:** A skill that says nothing about a missing test command.
- **Eval:** a skill that runs a command and says nothing about its failure, which the skill judge must flag.
- **Source:**
  - own (doc 10 checklist item 7)

### CORE-SKILL-11 · SKILL.md stays under 500 lines

- **Kind:** floor
- **Status:** retired
- **Replaced by:** CORE-TEMPLATE-02
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** `SKILL.md` is under 500 lines. Detail that only some runs need moves to reference files.
- **Why:** The whole file loads every time the skill runs. Rarely needed text is paid for on every run.
- **Check:** Count the lines.
- **Good:** A 180-line `SKILL.md` with the format details in `references/formats.md`.
- **Bad:** A 700-line `SKILL.md` with three domains inline.
- **Eval:** a 520-line `SKILL.md`, which the skill judge must flag.
- **Tool:** `wc -l SKILL.md`
- **Source:**
  - `anthropics/skills@ca45fc4 skills/skill-creator/SKILL.md` (Apache-2.0)
  - own (doc 10 checklist item 12)

### CORE-TEMPLATE-01 · A template cites rules by ID and never writes their text

- **Kind:** floor
- **Status:** retired
- **Replaced by:** CORE-TEMPLATE-05
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** A skill is written as a template, `SKILL.tmpl.md`, in its own folder. A step cites a rule's ID only where
  it depends on that rule, and never writes a rule's text. Its `metadata.roles` names the roles it serves.
  Its `metadata.areas` names every area its work touches, or is `rest` for the one skill of a job that takes every
  area no other skill of the job lists. Rule text reaches the agent only through the copies HW-RULE-01 allows.
- **Why:** Rule text written by hand goes stale when the rule changes, and the agent then sees two versions. A copy
  the build makes is checked against the rulebook on every pull request.
- **Check:** Is every sentence in the template that says how work must be done in general either a cited ID or a
  step? Is the file named `SKILL.tmpl.md`, and does it declare `metadata.roles` and `metadata.areas`?
- **Good:** "4. Name each test as CORE-TEST-03 asks.", in an implementer template with `areas: rest`.
- **Bad:** "4. Test names must state the scenario and the expected outcome.", written into the template.
- **Eval:** a template that restates a rule without its ID, which the skill judge must flag.
- **Source:**
  - own (CORE-SKILL-06)
  - `exepex/stratum@cc3ea82 AGENTS.md` ST-AG-18 (Apache-2.0)

### CORE-TEMPLATE-04 · A skill's first step reads its rules text

- **Kind:** floor
- **Status:** retired
- **Replaced by:** CORE-TEMPLATE-06
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** The first step of every template reads the run's rules texts, `rules-text-<skill>.<stack>.md` beside
  `rules.md`: one for each stack whose code the work touches, or every stack's when it touches no stack's code. It
  tells the agent to apply every rule in them and in the skill's copied rules. Where a rules text marks a copied
  rule as replaced or waived, or binds a decision point, the rules text wins. If a file is missing, the step runs
  the standards reader's command to make it; if that cannot run, it writes `rules.md` and the rules texts by reading
  and marks them `not verified`. The claims or verdict quote each file's read-back block, which names its stack.
- **Why:** Rules of the language, company, department, team and application layers, overrides and decision point
  bindings reach the agent only through these files. A skill that never reads them applies only the core rules.
- **Check:** Is the first step of the template the read of the rules texts, with which stacks to read and the
  missing-file path, and does it say a rules text wins over a copied rule? Does the output step quote each read-back
  block?
- **Good:** "1. Read `rules-text-invoice-writer.<stack>.md` beside `rules.md` for each stack whose code the work
  touches (every stack's when it touches none), making it with the standards reader's command if it is missing.
  Apply every rule in them and in Rules above; where one replaces, waives or binds a rule above, it wins." and a last
  step: "Quote the read-back block of each rules text in the claims."
- **Bad:** A template whose first step is "Read the story", with no read of the rules texts, one that reads a single
  rules text whatever the work touches, or one that never says a rules text wins over a copied rule it replaces or
  waives.
- **Eval:** a template with no rules-text step, one that reads a single rules text whatever the work touches, and
  one whose rules-text step does not say the rules text wins, which the skill judge must flag.
- **Source:**
  - own (CORE-SKILL-06)
