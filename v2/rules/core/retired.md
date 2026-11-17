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
