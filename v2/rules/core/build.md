# CORE-BUILD · Skill templates and release files

Principles layer, area `BUILD`. A skill is written once, as a template that cites rule IDs. A build script makes the
release skill from it, with the rule text that reaches the skill copied in. These rules govern the template and the
release files. What a good skill says is area `SKILL` ([skill.md](skill.md)); the whole set of skills is area
`CATALOG` ([catalog.md](catalog.md)).

These rules replace CORE-SKILL-02, CORE-SKILL-06 and CORE-SKILL-11, which a later change retires. The design is in
the skills plan, section 4 ("Templates and release files").

All text below is written new. Each Source names where the idea came from; `own` marks harnesswright's own text,
with the older rule it carries over.

### CORE-BUILD-01 · A template cites rules by ID and never writes their text

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** A skill is written as a template, `SKILL.tmpl.md`, in its own folder. A step cites a rule's ID only where
  it depends on that rule. The template never writes a rule's text (HW-RULE-01). Its `metadata.roles` names the roles
  it serves, and its `metadata.areas` names the areas whose rules it needs, or is `rest`. Only the build script
  copies rule text, into `release/`.
- **Why:** Rule text written by hand goes stale when the rule changes, and the agent then sees two versions. A copy
  the build makes is checked against the rulebook on every pull request.
- **Check:** Is every sentence in the template that says how work must be done in general either a cited ID or a
  step? Is the file named `SKILL.tmpl.md`, and does it declare `metadata.roles` and `metadata.areas`?
- **Good:** "4. Name each test as CORE-TEST-03 asks.", with `roles: implementer` and `areas: NAME, TEST`.
- **Bad:** "4. Test names must state the scenario and the expected outcome.", written into the template.
- **Eval:** a template that restates a rule without its ID, which the skill judge must flag.
- **Source:**
  - own (CORE-SKILL-06)
  - `exepex/stratum@cc3ea82 AGENTS.md` ST-AG-18 (Apache-2.0)

### CORE-BUILD-02 · A template stays under 500 lines; a release skill stays within its ceilings

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** `SKILL.tmpl.md` is under 500 lines. Detail that only some runs need moves to reference files. The release
  `SKILL.md` has no line limit, but its copied floors and the rest of its text each stay at or under 30,000
  characters, counted by the build. Only the owner raises a ceiling, with eval token counts as evidence. A skill over
  the second ceiling lists fewer areas or is split where its job runs in steps.
- **Why:** The whole file loads every time the skill runs. Text past what the agent can follow is paid for and then
  skipped.
- **Check:** Count the template's lines. Read the sizes the build reports for the release skill.
- **Good:** A 180-line template whose release skill reports 6,000 characters of floors and 21,000 of other text.
- **Bad:** A 700-line template, or a release skill whose other text is 38,000 characters.
- **Eval:** a 520-line template, which the skill judge must flag.
- **Tool:** the release check script
- **Source:**
  - own (CORE-SKILL-11)
  - `anthropics/skills@ca45fc4 skills/skill-creator/SKILL.md` (Apache-2.0)

### CORE-BUILD-03 · Template and release frontmatter use only standard fields, within their limits

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** The frontmatter of `SKILL.tmpl.md` and of its release `SKILL.md` holds only `name`, `description` and
  optionally `license`, `compatibility` and `metadata` (string values only). `name` matches both the template folder
  and the release folder, and has at most 64 lowercase letters, digits and single hyphens. `description` has at most
  1024 characters and no `<` or `>`. `compatibility` has at most 500 characters. Host-specific fields, including
  `allowed-tools`, live in adapters.
- **Why:** Hosts reject or treat differently anything outside the Agent Skills specification, and hosts load the
  release file, not the template.
- **Check:** Run the release check script, or read both frontmatters against this list.
- **Good:** `name: claims-writer` in `v2/skills/claims-writer/SKILL.tmpl.md` and `release/claims-writer/SKILL.md`.
- **Bad:** `name: Claims Writer` with an `allowed-tools` field, or a template folder named `claims`.
- **Eval:** a template whose `name` has capitals and does not match its folder, which the skill judge must flag.
- **Source:**
  - own (CORE-SKILL-02; HW-PORT-01)
  - `anthropics/skills@ca45fc4 skills/skill-creator/scripts/quick_validate.py` (Apache-2.0)
