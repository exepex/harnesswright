# CORE-SKILL · Writing a skill

Principles layer, area `SKILL`. These rules say what a good skill is. They apply to every skill: harnesswright's
own and the skills a company, department or team writes. A more specific layer may override a principle with a
stated reason and may tighten a floor, never loosen it ([03 · Standards](../../../docs/design/03-standards.md)).

How skills are tested and judged is area `EVAL`. How rules are made and kept is area `RULE`. Both come in later
changes.

Source short forms:

- `skill-creator`: `anthropics/skills@ca45fc4 skills/skill-creator/` (Apache-2.0)
- `writing-skills`: `obra/superpowers@2ce8aa1 skills/writing-skills/` (MIT)
- `stratum`: `exepex/stratum@cc3ea82` (Apache-2.0)

All text below is written new. Sources gave ideas only.

### CORE-SKILL-01 · A skill exists only for a reusable job

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** Write a skill only for a job that recurs across tasks or repositories. A one-off fix, one project's
  facts, or a check a script can make is not a skill: it is a task, an application rule or a script.
- **Why:** Every skill costs tokens each time agents scan the list. A skill that never recurs is pure cost.
- **Check:** Name two different tasks that would use the skill. If you cannot, it fails.
- **Good:** `claims-writer`: every finished story needs its claims written.
- **Bad:** `fix-login-timeout-march`: one bug, fixed once.
- **Eval:** a proposed skill for a single bug fix, which the skill judge must reject.
- **Source:** `writing-skills` SKILL.md

### CORE-SKILL-02 · The frontmatter uses only standard fields, within their limits

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** The frontmatter holds only `name`, `description` and optionally `license`, `compatibility` and
  `metadata` (string values only). `name` matches the folder name and has at most 64 lowercase letters, digits and
  single hyphens. `description` has at most 1024 characters and no `<` or `>`. `compatibility` has at most 500
  characters. Host-specific fields, including `allowed-tools`, live in adapters.
- **Why:** Hosts reject or treat differently anything outside the Agent Skills specification.
- **Check:** Run the frontmatter check script, or read the frontmatter against this list.
- **Good:** `name: claims-writer` in folder `skills/claims-writer/`.
- **Bad:** `name: Claims Writer` with `allowed-tools: Bash` in folder `skills/claims/`.
- **Eval:** a skill whose `name` has capitals and does not match its folder, which the skill judge must flag.
- **Source:** `skill-creator` scripts/quick_validate.py; `writing-skills` SKILL.md; own (HW-PORT-01)

### CORE-SKILL-03 · The description says what the skill does and when to use it

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** The description says in one or two sentences what the skill does, then when to use it, in the words an
  agent would search for: the problem, the symptoms, the file types. It names the nearby jobs it is not for. It
  does not summarise the steps. It names a technology only when the skill is specific to it.
- **Why:** The description is the only text an agent reads before choosing a skill. A vague one is never chosen; a
  step summary tempts the agent to follow the summary and skip the skill.
- **Check:** From the description alone, could an agent tell this skill apart from its nearest neighbour?
- **Good:** "Writes the claims for a finished story: each acceptance criterion with fresh evidence. Use when a story
  is finished and goes to the story judge. Not for writing code, stories or pull request descriptions."
- **Bad:** "Helps with documentation. First reads the diff, then runs tests, then writes a file."
- **Eval:** a skill whose description lists its steps and names no near miss, which the skill judge must flag.
- **Source:** `skill-creator` SKILL.md; `writing-skills` references/discovery.md; own (doc 10 checklist item 2)

### CORE-SKILL-04 · A skill states its purpose, limits and inputs

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** The body opens with what the skill does, what it does not do, what inputs it needs, and what to do when
  an input is missing.
- **Why:** An agent missing an input guesses it. A guessed input gives a confident wrong result.
- **Check:** For each input, does the skill say where it comes from and what happens without it?
- **Good:** "Needs the story file. If there is none, stop and ask for it."
- **Bad:** A skill that uses "the acceptance criteria" without saying where they are.
- **Eval:** a skill that uses an input without saying where it comes from, which the skill judge must flag.
- **Source:** own (doc 10 checklist items 1 and 3)

### CORE-SKILL-05 · Steps are numbered, imperative and checkable

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** Write the procedure as numbered steps. Each step is a command, and each says how the agent knows it is
  done.
- **Why:** A step with no end condition is skipped or repeated, and nobody can tell which.
- **Check:** For each step, can a reviewer tell from the run whether it happened?
- **Good:** "3. Run the tests. Done when the output shows zero failures."
- **Bad:** "Make sure the tests are in good shape."
- **Eval:** a skill with an unnumbered paragraph of advice, which the skill judge must flag.
- **Source:** `writing-skills` references/anthropic-best-practices.md; own (doc 10 checklist item 4)

### CORE-SKILL-06 · A skill cites the rules it applies by ID

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** A skill tells the agent to apply the resolved rules whose Applies to names its role. It cites a rule ID
  only where one step depends on that rule. It never writes a rule's text (HW-RULE-01).
- **Why:** A copied rule goes stale when the rule changes, and the agent then sees two versions.
- **Check:** Is every sentence that says how work must be done in general either a cited ID or a step?
- **Good:** "4. Name each test as CORE-TEST-03 asks."
- **Bad:** "4. Test names must state the scenario and the expected outcome."
- **Eval:** a skill that restates a rule without its ID, which the skill judge must flag.
- **Source:** `stratum` AGENTS.md (ST-AG-18); own (doc 10 checklist item 5)

### CORE-SKILL-07 · A skill proves its own result before it reports

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** Each skill has a verification step that names the command, test or check that proves the job is done.
  Batch or destructive work writes a plan, checks the plan, acts, then verifies, and repeats until the check
  passes.
- **Why:** Agents claim "done" without proof. The step makes the proof part of the job.
- **Check:** Does the skill name a check whose output shows success or failure?
- **Good:** "6. Run `claims_check.py`. Done when it reports no missing criterion."
- **Bad:** "6. Check your work."
- **Eval:** a skill whose last step is "check your work", which the skill judge must flag.
- **Source:** `writing-skills` references/anthropic-best-practices.md; own (doc 10 checklist item 6)

### CORE-SKILL-08 · A skill says what to do when a step fails

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** For each step that can fail, the skill says what to do: retry, use another route, or stop and ask one
  clear question. It never lets the agent skip the step silently.
- **Why:** Without a stated path, an agent skips the failed step and reports success.
- **Check:** For each step that can fail, is there a stated next action?
- **Good:** "If the test command is not found, stop and ask which command runs the tests."
- **Bad:** A skill that says nothing about a missing test command.
- **Eval:** a skill that runs a command and says nothing about its failure, which the skill judge must flag.
- **Source:** own (doc 10 checklist item 7)

### CORE-SKILL-09 · Output follows its contract

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** A skill that hands work to another role writes it in that hand-over's contract and names the contract.
  It states every output format exactly.
- **Why:** The next role reads fields, not prose. A missing field is a lost result.
- **Check:** Does each output name its contract or give its exact format?
- **Good:** "Write the claims in the claims format of 06 · Contracts."
- **Bad:** "Summarise what you did."
- **Eval:** a skill output with a missing contract field, which the skill judge must flag.
- **Source:** `skill-creator` SKILL.md; own (HW-PORT-06, doc 10 checklist item 8)

### CORE-SKILL-10 · One good and one bad example

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** A skill gives at least one complete good example and one bad example, in the most relevant language.
  It does not repeat the same example in several languages.
- **Why:** One real example teaches the shape faster than rules. Copies in several languages cost tokens and teach
  nothing more.
- **Check:** Is there one complete good example and one bad example?
- **Good:** One full claims file for a real story, and one with an unproved claim.
- **Bad:** The same snippet in Java, Python and Go, with no bad example.
- **Eval:** a skill with no bad example, which the skill judge must flag.
- **Source:** `writing-skills` SKILL.md; own (doc 10 checklist item 9)

### CORE-SKILL-11 · SKILL.md stays under 500 lines

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** `SKILL.md` is under 500 lines. Detail that only some runs need moves to reference files.
- **Why:** The whole file loads every time the skill runs. Rarely needed text is paid for on every run.
- **Check:** Count the lines.
- **Good:** A 180-line `SKILL.md` with the format details in `references/formats.md`.
- **Bad:** A 700-line `SKILL.md` with three domains inline.
- **Eval:** a 520-line `SKILL.md`, which the skill judge must flag.
- **Tool:** `wc -l SKILL.md`
- **Source:** `skill-creator` SKILL.md; own (doc 10 checklist item 12)

### CORE-SKILL-12 · Each reference is linked once, with when to read it

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** `SKILL.md` links each reference file directly and says when to read it. A reference never sends the
  reader to a further file for content it needs. A skill with several domains keeps each in its own reference.
  Principles and short patterns stay in `SKILL.md`.
- **Why:** Agents read a file only when told when to. A chain of references is read halfway or not at all.
- **Check:** Is every reference linked from `SKILL.md` with a "read when", and does none depend on another?
- **Good:** "Read `references/aws.md` when the target is AWS."
- **Bad:** A `references/` file that no step mentions, or `a.md` that says "see `b.md` for the steps".
- **Eval:** a skill with an unlinked reference file, which the skill judge must flag.
- **Source:** `skill-creator` SKILL.md; `writing-skills` references/anthropic-best-practices.md

### CORE-SKILL-13 · Every sentence earns its place

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** A skill holds only what the agent does not already know and needs for this job. It holds no story of how
  a problem was once solved, no history or "old way" section, and nothing a date will make false.
- **Why:** Every sentence is read on every run. Text the agent already knows costs tokens and buries the steps.
- **Check:** For each paragraph, would an agent without it do the job worse?
- **Good:** "Use the `--frozen` flag; without it the lockfile is rewritten."
- **Bad:** "Python is a programming language. Last March we found that…"
- **Eval:** a skill with a section explaining what a unit test is, which the skill judge must flag.
- **Source:** `writing-skills` SKILL.md and references/anthropic-best-practices.md; `stratum`
  docs/agents/documentation.md (ST-DOC-03)

### CORE-SKILL-14 · One default, not a menu

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** Where several ways work, the skill gives one default and names the case for the alternative.
- **Why:** A menu makes each agent pick differently, so runs stop being comparable.
- **Check:** Does any step list options without saying which one to use?
- **Good:** "Use `pytest`. Use `unittest` only when the repository has no `pytest`."
- **Bad:** "You can use pytest, unittest or nose."
- **Eval:** a skill step that lists three tools with no default, which the skill judge must flag.
- **Source:** `writing-skills` references/anthropic-best-practices.md

### CORE-SKILL-15 · Exact work gets an exact command

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** Where one wrong move breaks the result, such as a migration or a release, the skill gives the exact
  command or script. Where many answers are fine, it gives the goal and the checks.
- **Why:** Freedom on fragile work causes damage; exact scripts on open work produce poor answers.
- **Check:** For each fragile step, is there an exact command?
- **Good:** "Run `python3 scripts/migrate.py --dry-run` first."
- **Bad:** "Migrate the database carefully."
- **Eval:** a skill that describes a migration in prose only, which the skill judge must flag.
- **Source:** `writing-skills` references/anthropic-best-practices.md

### CORE-SKILL-16 · Guidance fits the failure it fixes

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** Match the form of guidance to the failure seen in testing: a skipped step gets a check that fails
  without it; a wrong shape gets a format or contract; a missing part gets a required slot; behaviour that depends
  on a case gets a condition on an observable fact. Add warning prose only when none of these fits.
- **Why:** More prose does not stop a skipped step. A check does.
- **Check:** For each warning in capitals or "never", could a check, format or condition do the job instead?
- **Good:** A required `Evidence:` field that the check script fails when empty.
- **Bad:** "IMPORTANT: ALWAYS include evidence!!"
- **Eval:** a skill that answers a skipped-evidence failure with capitalised warnings, which the skill judge must
  flag.
- **Source:** `writing-skills` SKILL.md; `stratum` AGENTS.md (ST-AG-19)

### CORE-SKILL-17 · Another skill is cited by name, with its weight

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** A skill that relies on another names it and says whether it is required first or background. It never
  copies the other skill's steps and never forces it to load.
- **Why:** Copied steps drift apart; forced loading spends tokens on runs that do not need it.
- **Check:** Is every other skill named with "required" or "background"?
- **Good:** "Required first: the claims-writer skill."
- **Bad:** Five steps pasted from claims-writer.
- **Eval:** a skill that pastes another skill's steps, which the skill judge must flag.
- **Source:** `writing-skills` references/discovery.md

### CORE-SKILL-18 · A skill names no host tool and no model

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** The body uses plain verbs ("run the command", "read the file", "start an independent reviewer"). It
  names no host tool, no slash command and no concrete model; it uses the model classes `deep`, `standard` and
  `fast`. Every instruction is explicit and relies on no habit of one model.
- **Why:** The same skill must behave the same on every host. A host tool name fails on the others.
- **Check:** Search the body for host tool names, slash commands and model names.
- **Good:** "Start an independent reviewer on a `deep` model."
- **Bad:** "Use the Task tool with `model: opus`."
- **Eval:** a skill that names a host tool and a model, which the skill judge must flag.
- **Source:** own (HW-PORT-02, HW-PORT-07)

### CORE-SKILL-19 · A step that needs a host feature names the capability

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** A step that needs a host feature names the capability. Where the step needs no independence, such as
  parallel work, the skill gives a fallback that works in one agent, in sequence. Where it needs independence (a
  reviewer, judge, verifier or panel voter), it runs in a fresh, separate agent that gets only the contracts and
  the change. If the host cannot start one, the work stops and asks the owner. There is no in-session fallback for
  independence.
- **Why:** A worker that checks its own work passes its own mistakes.
- **Check:** Does each independent step require a separate agent, with no "or do it yourself" path?
- **Good:** "Start a separate judge. If you cannot, stop and tell the owner."
- **Bad:** "Start a judge, or review the change yourself if sub-agents are not available."
- **Eval:** a skill that lets the worker judge itself when no sub-agent is available, which the skill judge must
  flag.
- **Source:** own (HW-PORT-03)

### CORE-SKILL-20 · Logic that must agree everywhere is a script

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** A check that must give the same result on every host, such as counting lines or checking a format, is
  a bundled script, not prose. Scripts use Python 3 with only the standard library, make no network calls, are
  deterministic and run as `python3 <path>`. Each mention of a script says whether to run it or read it. A skill
  never tells the agent to install a package.
- **Why:** Prose checks differ from model to model. An installed package differs from machine to machine.
- **Check:** Read each bundled script's imports and calls, and each step that mentions it.
- **Good:** "Run `python3 scripts/check.py claims.md`."
- **Bad:** "Run `pip install pyyaml`, then `./check`."
- **Eval:** a skill whose script imports a third-party package, which the skill judge must flag.
- **Source:** `writing-skills` SKILL.md and references/anthropic-best-practices.md; own (HW-PORT-04)

### CORE-SKILL-21 · Every script step has a no-script fallback

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** Every step that runs a bundled script says what to do when the script must not or cannot run: do the
  check by reading what you can, mark each result the script would have checked `not verified`, tell the person
  first that the check did not run, and never claim its result.
- **Why:** Some teams forbid scripts. Without a fallback, an agent fakes the result.
- **Check:** Does each script step have a fallback that marks results `not verified`?
- **Good:** "If the script cannot run, check the fields by reading and mark the result `not verified`."
- **Bad:** A script step with no fallback.
- **Eval:** a skill with a script step and no fallback, which the skill judge must flag.
- **Source:** own (HW-PORT-08)

### CORE-SKILL-22 · A skill does only what it says

- **Kind:** floor
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** A skill's content and scripts match its stated purpose. It holds no hidden purpose, no exploit or
  data-sending code, and no false urgency, guilt or flattery used to get compliance.
- **Why:** Teams run skills with their own access. A hidden step runs with that access.
- **Check:** Read every file. Does any part do something the description does not say?
- **Good:** A test-writing skill whose script only reads the test folder.
- **Bad:** A formatting skill whose script posts the repository to a web address.
- **Eval:** a skill whose script makes a network call its description never mentions, which the skill judge must
  flag.
- **Source:** `skill-creator` SKILL.md; `writing-skills` references/persuasion-principles.md

### CORE-SKILL-23 · Every skill is listed where any host can find it

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** The repository's agent instructions file lists every skill with its path and when to use it.
- **Why:** Some hosts do not load skills on their own. Unlisted skills are never used there.
- **Check:** Is every skill folder listed, and does every listed path exist?
- **Good:** A row with `claims-writer`, its path and its "use when".
- **Bad:** A new skill folder with no row.
- **Eval:** a repository with an unlisted skill, which the skill judge must flag.
- **Source:** own (HW-PORT-05)
