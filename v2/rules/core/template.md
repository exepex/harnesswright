# CORE-TEMPLATE · Skill templates and release files

Principles layer, area `TEMPLATE`. A skill is written once, as a template that cites rule IDs. A build script makes
the release skill from it, with the rule text that reaches the skill copied in. At run time the skill also reads a
rules text with the rules of the more specific layers. These rules govern the template and the release skill. What a
good skill says is area `SKILL` ([skill.md](skill.md)); the whole set of skills is area `CATALOG`
([catalog.md](catalog.md)).

CORE-TEMPLATE-01 to 03 replace CORE-SKILL-06, CORE-SKILL-11 and CORE-SKILL-02, which a later change retires.

All text below is written new. Each Source names where the idea came from; `own` marks harnesswright's own text,
with the older rule it carries over.

### CORE-TEMPLATE-01 · A template cites rules by ID and never writes their text

- **Kind:** floor
- **Status:** active
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

### CORE-TEMPLATE-02 · A template stays under 500 lines; a release skill stays within its ceilings

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** `SKILL.tmpl.md` is under 500 lines. Detail that only some runs need moves to reference files. The release
  `SKILL.md` has no line limit, but its copied floors and the rest of its text each stay at or under 30,000
  characters (Unicode code points), counted by the build. A skill is never made to fit by dropping an area its work
  touches. Over the second ceiling, the skill is split where its job runs in steps; otherwise, and over the floors
  ceiling, the owner decides on eval evidence. A raised ceiling is a new rule with a new ID.
- **Why:** The whole file loads every time the skill runs. Text past what the agent can follow is paid for and then
  skipped, and a dropped area silently removes rules from the run.
- **Check:** Count the template's lines. Read the sizes the build reports for the release skill. Does the template
  list every area its work touches?
- **Good:** A 180-line template whose release skill reports 6,000 characters of floors and 21,000 of other text.
- **Bad:** A 700-line template, or a release skill whose other text is 38,000 characters, or an area removed to fit.
- **Eval:** a 520-line template, and a template whose release text is over a ceiling, which the skill judge must
  flag.
- **Tool:** `wc -l SKILL.tmpl.md`
- **Source:**
  - own (CORE-SKILL-11)
  - `anthropics/skills@ca45fc4 skills/skill-creator/SKILL.md` (Apache-2.0)

### CORE-TEMPLATE-03 · Template and release frontmatter use only standard fields, within their limits

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
- **Check:** Read both frontmatters against this list, or run the frontmatter check script.
- **Good:** `name: claims-writer` in `v2/skills/claims-writer/SKILL.tmpl.md` and `release/claims-writer/SKILL.md`.
- **Bad:** `name: Claims Writer` with an `allowed-tools` field, or a template folder named `claims`.
- **Eval:** a template whose `name` has capitals and an `allowed-tools` field, which the skill judge must flag.
- **Source:**
  - own (CORE-SKILL-02; HW-PORT-01)
  - `anthropics/skills@ca45fc4 skills/skill-creator/scripts/quick_validate.py` (Apache-2.0)

### CORE-TEMPLATE-04 · A skill's first step reads its rules text

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** The first step of every template reads the run's rules text, `rules-text-<skill>.md` beside `rules.md`,
  and tells the agent to apply every rule in it and in the skill's copied rules. If the file is missing, the step
  runs the standards reader's command to make it; if that cannot run, it writes the file by reading and marks it
  `not verified`. The claims or verdict quote the file's read-back block.
- **Why:** Rules of the language, company, department, team and application layers, overrides and decision point
  bindings reach the agent only through this file. A skill that never reads it applies only the core rules.
- **Check:** Is the first step of the template the read of the rules text, with the missing-file path? Does the
  output step quote the read-back block?
- **Good:** "1. Read `rules-text-claims-writer.md` beside `rules.md` and apply every rule in it and in Rules above."
- **Bad:** A template whose first step is "Read the story", with no read of the rules text.
- **Eval:** a template with no rules-text step, which the skill judge must flag.
- **Source:**
  - own (CORE-SKILL-06)
