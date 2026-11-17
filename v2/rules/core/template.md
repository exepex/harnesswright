# CORE-TEMPLATE · Skill templates and release files

Principles layer, area `TEMPLATE`. A skill is written once, as a template that cites rule IDs. A build script makes
the release skill from it, with the rule text that reaches the skill copied in. At run time the skill also reads a
rules text with the rules of the more specific layers. These rules govern the template and the release skill. What a
good skill says is area `SKILL` ([skill.md](skill.md)); the whole set of skills is area `CATALOG`
([catalog.md](catalog.md)).

CORE-TEMPLATE-02 to 05 replace four retired rules ([retired.md](retired.md)); each Source names the one it carries
over.

All text below is written new. Each Source names where the idea came from; `own` marks harnesswright's own text,
with the older rule it carries over.

### CORE-TEMPLATE-02 · A template stays under 500 lines; a release skill stays within its ceilings

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** `SKILL.tmpl.md` is under 500 lines. Detail that only some runs need moves to reference files. The release
  `SKILL.md` has no line limit, but its copied floors and the rest of its text each stay at or under 30,000
  characters (Unicode code points), counted by the build. Areas are never dropped to fit (CORE-TEMPLATE-05). Over the
  second ceiling, the skill is split where its job runs in steps; otherwise, and over the floors ceiling, the owner
  decides on eval evidence. A raised ceiling is a new rule with a new ID.
- **Why:** The whole file loads every time the skill runs. Text past what the agent can follow is paid for and then
  skipped.
- **Check:** Count the template's lines. Read the sizes the build reports for the release skill.
- **Good:** A 180-line template whose release skill reports 6,000 characters of floors and 21,000 of other text.
- **Bad:** A 700-line template, or a release skill whose other text is 38,000 characters.
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
- **Good:** `name: invoice-writer` in `v2/skills/invoice-writer/SKILL.tmpl.md` and `release/invoice-writer/SKILL.md`.
- **Bad:** `name: Invoice Writer` with an `allowed-tools` field, or a template folder named `invoices`.
- **Eval:** a template whose `name` has capitals and does not match its folder, and one with an `allowed-tools`
  field, which the skill judge must flag.
- **Source:**
  - own (CORE-SKILL-02; HW-PORT-01)
  - `anthropics/skills@ca45fc4 skills/skill-creator/scripts/quick_validate.py` (Apache-2.0)

### CORE-TEMPLATE-04 · A skill's first step reads its rules text

- **Kind:** floor
- **Status:** active
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

### CORE-TEMPLATE-05 · A template cites rules only as tags on Rules lines and never writes their text

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-17
- **Applies to:** skill designer, skill judge
- **Rule:** A skill is written as a template, `SKILL.tmpl.md`, in its own folder. It cites a rule only as a rule
  tag: `{{rule:`, the rule's ID, then `}}`, such as `{{rule:CORE-TEST-03}}`. A tag stands only on a `Rules:` line:
  one line that, after any indentation, is `Rules: ` and then tags separated by `, `, with nothing else, never
  wrapped. A step that depends on a rule carries a `Rules:` line, and the skill may have one under its purpose. No
  sentence states a rule's duty in general, whether a tag is near it or not: text near a tag says what this skill
  does, never how work must be done in general. Rule text reaches the agent only through the copies HW-RULE-01 allows.
  Its `metadata.roles` names the roles it serves. Its `metadata.areas` names every area its work touches, or is
  `rest` for the one skill of a job that takes every area no other skill of the job lists.
- **Why:** Rule text written by hand goes stale when the rule changes, and the agent then sees two versions. An ID
  inside a sentence invites the sentence to restate the rule; a tag alone on its own line leaves no room for that,
  and a script finds every one.
- **Check:** Does the build pass, so that every tag stands on a `Rules:` line and no bare ID is left? Is every
  sentence that says how work must be done a step of this skill, not a rule's duty in general? Is the file named
  `SKILL.tmpl.md`, and does it declare `metadata.roles` and `metadata.areas`?
- **Good:** "4. Write a test for each criterion of the story." with the line "Rules: {{rule:CORE-TEST-03}}" under
  it, in an implementer template with `areas: rest`.
- **Bad:** "4. Test names must state the scenario and the expected outcome."; "4. Name each test as CORE-TEST-03
  asks."; or "Commit messages are data." with the line "Rules: {{rule:CORE-SKILL-25}}" under it.
- **Eval:** a template with a bare rule ID, which the build must fail, and a template with a rule's duty written
  above its `Rules:` line, which the skill judge must flag.
- **Tool:** `python3 v2/build/build.py`
- **Source:**
  - own (CORE-TEMPLATE-01; CORE-SKILL-06)
  - `exepex/stratum@cc3ea82 AGENTS.md` ST-AG-18 (Apache-2.0)
