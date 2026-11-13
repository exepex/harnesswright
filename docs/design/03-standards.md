# 03 · Standards and rules

Standards say what good work looks like: code, tests, documentation, configuration and security. They are written
in layers. General principles are written once, and an application's own way of working can still win. The words
used here are defined in the [design README](README.md).

## The six layers

| Layer | ID prefix | Holds | Owned by | Lives in |
|---|---|---|---|---|
| 1 Principles | `CORE` | Principles, floors and decision points | harnesswright | `standards/core/` |
| 2 Language, framework | `JAVA`, `JAVA-SPRING`, `PY`, `GO`, `TS`, … | Idioms, decision points, defaults and the toolchain | harnesswright | `standards/languages/<language>/` |
| 3 Company | `COMP-<name>` | Choices and floors for all its teams | The company | The company's own repository |
| 4 Department | `DEPT-<name>` | Choices and floors for its teams | The department | The company's repository |
| 5 Team | `TEAM-<name>` | Choices and floors for its applications | The team | The company's repository |
| 6 Application | `APP` | Facts, choices and floors of one codebase | The application owner | `.harness/standards/` in the application |

- Only the principles layer is required. Layers 3 to 5 are optional.
- A framework is a sub-layer of its language, such as `JAVA-SPRING` under `JAVA`. It extends the language.
- There is one department level. Each application has one owning team.
- The company picks the names for layers 3 to 5 (HW-RULE-03).
- Each folder of layers 3 to 5 holds a `layer.yaml`, written by hand, that names the layer's owner and version. The
  application owner is named in the profile, and the owner of layers 1 and 2 in `AGENTS.md`.
- The profile names the layers an application uses, in order. Layers 1 and 2 come with the installed harnesswright
  release, pinned by its version. Each layer 3 to 5 is a folder with a pinned version. A missing folder or a
  different version stops the run. See [07 · Repository profile](07-repo-profile.md).

## Precedence

1. The more specific layer wins: application over team, team over department, department over company, company
   over language, language over principles.
2. A rule that changes another rule says so (HW-RULE-05).
3. A floor is never loosened (HW-RULE-06). A more specific layer may only tighten it.
4. When two layers contradict each other without saying so, agents stop and ask the layer owners. They do not
   choose a side.
5. When a layer loosens a floor, the change fails and the flow stops.

## Kinds of rule

| Kind | Meaning | Example | May live in | A more specific layer may |
|---|---|---|---|---|
| **Principle** | An outcome every codebase should reach | "A unit has one reason to change" | Principles layer | Override it, with a stated reason |
| **Floor** | A minimum that is never traded away | "No secret appears in code, configuration, logs or tests" | Any layer | Only tighten it |
| **Idiom** | How a principle is done well in one language | "Go: return errors as values; wrap them with context" | Language and framework layers | Override it |
| **Choice** | One valid option among several | "Generate boilerplate with Lombok" | Language and framework layers (as a default), and layers 3 to 6 | Override it |

A choice either binds a decision point or stands alone when no point exists ("money is always in cents"). To tell a
choice from a principle, ask: "Would another reasonable team choose otherwise?" If yes, it is a choice. "Use
Lombok" is a choice; "Do not hand-write boilerplate that a language feature or a generator can produce" is a
principle.

A company that wants a principle kept in all its teams makes it a company floor.

## Decision points

A decision point is a place where good teams choose differently. It has a default, and a more specific layer binds
it with a choice. Decision points live in the principles, language and framework layers, with IDs
`<LAYER>-DP-<NAME>`. A language layer sets its own default with a choice that binds the point.

| Decision point | Principles default | Example bindings |
|---|---|---|
| `CORE-DP-BOILERPLATE` | Use the language's own feature (records, data classes) | Lombok · hand-written accessors |
| `CORE-DP-MAPPING` | Plain mapping functions in a dedicated mapper unit | MapStruct · manual mappers |
| `CORE-DP-CONSTRUCTION` | Constructor; builder when there are several optional fields | Builder for all public types · constructor only |
| `CORE-DP-INJECTION` | Constructor injection | Setter injection · field injection |
| `CORE-DP-ERRORS` | The language's idiomatic error model | Checked exceptions · result types |
| `CORE-DP-TEST-STACK` | The language layer's default test tools | JUnit 5 + AssertJ · pytest |
| `CORE-DP-NULLS` | Make absence explicit in the type | `Optional` · nullability annotations |

## Rules about the rulebook

These rules govern every rule in every layer. The rule writer, the rule keeper and the skill judge cite them by ID
and never restate them. Like `HW-AG` and `HW-PORT`, they are harness rules: no layer may override them.

**HW-RULE-01 · One rule lives in one place.** A rule's text exists only in its standard. Skills, roles,
contracts, tests, adapters and agent instruction files cite its ID, and hold only steps, ID citations or pointers.
A sentence in them that says what code, tests, documentation or configuration must be like in general, without an
ID, is a restatement and a defect. The requirements of one piece of work, such as a story's acceptance criteria or
a quoted request, are not standards and are not restatements.
A skill is its template. Three kinds of file hold rule text and are copies, not a second source: the release skills a
build script generates from templates; the layer folders and roles file the build copies byte for byte into the
release (`release/rules/`, `release/roles.md`), so the standards reader can read them; and the
`rules-text-<skill>.md` file the standards reader writes beside `rules.md` for a run. A script proves each copy
exact. Release files are only ever generated; where scripts cannot run, the rules text is written by reading and
marked "not verified". None is edited by hand, and the restatement test above does not apply to them.

**HW-RULE-02 · Every rule has one kind,** from the table above, and lives only in a layer that kind allows. A
decision point lives only in the principles, language and framework layers.

**HW-RULE-03 · IDs are stable.** A rule's ID is `<LAYER>-<AREA>-<NN>`, such as `CORE-NAME-04`, `JAVA-TEST-02` or
`APP-CONF-01`. A decision point's ID is `<LAYER>-DP-<NAME>`. An ID is unique, never changes and is never reused. A
change of meaning needs a new ID. A wording fix keeps the ID. A name in layers 3 to 5 is one word with no hyphen,
so a script that knows the language prefixes and the areas can split every ID.

**HW-RULE-04 · Every rule has all its required parts.**

| Part | Required | Holds |
|---|---|---|
| ID, Title | Yes | The unique code; one line that says the rule |
| Kind | Yes | Principle, floor, idiom or choice |
| Status | Yes | `active`, `inferred` (waiting for a human to confirm) or `retired` |
| Review by | Yes | The date (`YYYY-MM-DD`) by which the rule's owner checks the rule is still right |
| Replaced by | When retired | The new IDs, comma-separated, or "no replacement" |
| Applies to | Yes | The roles that apply it, named as in [v2/roles.md](../../v2/roles.md), or `every role`, or both. This is the only map of which rules a role applies. |
| Rule, Why, Check | Yes | The rule in plain sentences; the reason; how a reviewer proves it is met or broken |
| Good, Bad | Yes | One example of each |
| Eval | Yes | The test case that proves a reviewer catches the Bad example |
| Source | Yes | `own`, or `<repository>@<commit> <path> (<licence>)` |
| Overrides, Binds or Tightens | Layers 2 to 6, when it changes another rule | The ID of the rule it changes; for Binds, the decision point's ID, a colon and the option it picks |
| Tool | No | A command that checks it mechanically |
| Exceptions | No | When it does not apply |

A decision point has: ID, Title, Status, Review by, Question, Options, Default, Why, Applies to, Source, and Replaced
by when retired. Options is a list with one item per option, written `` - `name`: what it means ``. Default
names exactly one of the Options in backticks, such as `` `records` ``; the standards reader stops on any other
Default.

**HW-RULE-05 · A change to another rule is stated.** A rule that changes a more general rule names it with
exactly one relation: `Overrides` (replaces a principle, idiom or choice; overriding a principle needs a stated
reason), `Binds` (picks one of a decision point's Options, named on the same line) or `Tightens` (makes a floor
stricter). The rule it changes is in a more general layer. A relation fits the kinds of both rules: `Tightens` goes
from a floor to a floor, `Binds` from a choice to a decision point, and `Overrides` from a principle, idiom or
choice to a principle, idiom or choice; anything else stops the run, so a floor is never loosened in two steps. A
silent contradiction is a defect.

**HW-RULE-06 · A floor is never loosened or waived.** No layer and no person may loosen a floor, override it or
waive it. The only way to change a floor is a new rule with a new ID in the layer that owns it, approved by that
layer's owner.

**HW-RULE-07 · A rule is retired, never deleted.** A retired rule keeps its ID and all its parts, gets status
`retired` and a Replaced by, and moves to the `retired.md` file of its layer folder, so area files hold only live
rules. `retired.md` is not an area; past 500 lines it splits into `retired-<area>.md` files. A replacement is added
in an earlier change than the retirement. Citations in the same repository are updated in the same change as the
retirement. Retiring a rule fails while any file still cites the old ID, other than the index, the retired rules
files, the Source of a rule named in its Replaced by, and `CHANGELOG.md` ([08 · Governance](08-governance.md)).

**HW-RULE-08 · The index is generated.** Each layer folder has an index (ID, title, kind, status, file), built by
a script from the rule headings. Nobody edits it by hand. Where scripts cannot run, the rule keeper builds it by
reading and marks it "not verified".

**HW-RULE-09 · Layers 1 and 2 use neutral words.** Principles and language rules use the words of the table in
"Language-neutral words", so every language can apply them.

## Rule format

Each standard covers one area in one layer and holds several rules. No standard is over 500 lines. A rule looks
like this:

```markdown
### CORE-TEST-03 · A test name states the scenario and the expected outcome

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** implementer, test writer, code reviewer, story judge
- **Rule:** Name each test after the situation it sets up and the result it expects, in plain words.
- **Why:** A failing test should tell the reader what broke without opening the test body.
- **Check:** Review question: "Can I tell from the name alone what failed?"
- **Good:** `rejectsOrderWhenStockIsInsufficient`
- **Bad:** `testOrder2`, `shouldWork`
- **Eval:** a case with a test named `testOrder2`, which the reviewer must flag
- **Source:** own
```

A rule in layers 2 to 6 that changes another rule adds one line: `**Overrides:** CORE-…`,
`**Binds:** CORE-DP-…: <option>` (such as `**Binds:** CORE-DP-BOILERPLATE: lombok`, where `lombok` is one of the
point's Options) or `**Tightens:** CORE-…`. A language layer's binding is that language's default.

## Areas

An area is one topic of rules. Each layer has at most one standard per area.

| Area | Covers |
|---|---|
| `WORK` | Duties every role has, as floors: report only what you verified, done means proven, and so on |
| `NAME` | Names of types, functions, variables, parameters, constants and tests |
| `DSGN` | Units and decomposition, SOLID, KISS, DRY, helpers, mappers, strategies, patterns, size limits |
| `FUNC` | Pure functions, immutability, side effects at the edges |
| `CONF` | Typed and validated configuration, defaults, no magic values |
| `ERR` | Error handling, timeouts, bounded resources, retries, resilience |
| `DOC` | Comments, API documentation, project documents |
| `TEST` | Unit and mock tests |
| `ITEST` | Integration, API and contract tests, test data |
| `PERF` | Performance and load tests, budgets for latency, throughput, memory and CPU |
| `SEC` | Secure coding: OWASP Top 10, input validation, secrets, dependencies |
| `OPS` | Observability, migrations, feature flags, rollback, runbooks |
| `PLAN` | What makes a plan, a story and acceptance criteria good |
| `DP` | Decision points |

## Language-neutral words

| Neutral word | Means | Java | Go | Python |
|---|---|---|---|---|
| unit | the smallest named piece of design | class | package or type | module or class |
| function | named behaviour | method | function or method | function or method |
| interface | a contract other code depends on | interface | interface | protocol |
| API documentation | the reader-facing description of a unit | Javadoc | doc comment | docstring |

HW-RULE-09 uses these neutral words.

## Existing applications

1. Onboarding, done by the team or its runtime, proposes the conventions the code follows as `inferred`
   application rules. A person confirms them once, in one batch. From then on they are ordinary application rules.
2. A convention that differs from a principle or idiom becomes an `Overrides` rule with its reason.
3. A convention that breaks a floor is never proposed as a rule. It is listed as a **known breach** (file, rule ID,
   date) for the application owner to confirm. A known breach is shown on every run.
4. New or changed code meets every floor. An untouched known breach is reported as a note, never a blocker.
5. A convention that conflicts with a company, department or team rule that is not a floor is reported to the
   application owner with three options: change the code, write an `Overrides` rule, or ask for a waiver. Onboarding
   writes none of them.

## Waivers

A **waiver** lets one application, or one story, not follow one rule that is not a floor, for a time. It records
the rule ID, the reason, an end date and who approved it. There is never a waiver for a floor (HW-RULE-06). An
application's waivers live in its profile ([07 · Repository profile](07-repo-profile.md)).

| Rule being overridden or waived | Who approves |
|---|---|
| A floor, in any layer | Nobody. A floor is never overridden or waived. |
| A principles, language or framework rule | The owner of the layer where the override lives, or the application owner for a waiver. The reason is recorded and shown in the rules text. |
| A company, department or team rule | The owner of the layer where the override or waiver lives **and** the owner of the rule's layer |

A waiver of an application rule is approved by the application owner. A story that skips one rule gets a waiver
scoped to that story, approved as the table says. It is recorded in the story before work starts and cited in the
claims.

## Resolving the rules for an application

The standards reader combines the layers with a Python script that uses only the standard library. Where scripts
cannot run, it does the same by reading, and marks the result "not verified".

**Inputs.** It first checks each folder's version against the profile (step 5). Then it reads these three inputs
and no other rules:

1. The **active** rules of each layer the profile lists. Rules with status `inferred` or `retired` are never read.
2. The **decision point bindings** in the profile. They count as bindings of the application layer.
3. The application's **approved waivers** whose end date has not passed. Story-scoped waivers are not read.

**Stacks.** No language outranks another, so each language the profile lists is resolved on its own, as one
stack: the principles layer, that language and its frameworks, then layers 3 to 6. A rule of layers 3 to 6 that
changes a rule of one language belongs to that language's stack only, and the profile's bindings apply in each
stack that holds their point. Where a language replaced a principles rule, its replacement stands in that rule's
place: a rule of layers 3 to 6 that names the principles rule changes the replacement in that stack. An
application with no language has one stack. The steps run once per stack.

**Steps.**

1. Start with the principles layer. Apply each listed layer, most general first: an override replaces a rule, a
   tightening makes a floor stricter, a binding picks a decision point's option and replaces any earlier binding of
   that point, and any other rule is added. A rule that changes a rule a more specific layer already replaced is a
   contradiction: it must change the rule that replaced it. A binding changes only by binding its point again, so
   an override never names a binding rule. A language or framework layer changes only principles rules and its own
   language's.
2. Apply the profile's bindings; each replaces any layer's binding of its point. A decision point bound more than
   once in the application layer, by rules or by the profile, is a contradiction.
3. An unbound decision point takes the language default, then the principles default.
4. Mark each waived rule with its waiver: reason, end date and approver. A waiver names a principle, idiom or
   choice that binds no decision point; a binding changes only by binding its point again. A waived rule that
   overrides another still replaces it. A story-scoped waiver is not an input: it lives in its story, and the story
   judge checks it there ([06 · Contracts](06-contracts.md)).
5. If two inputs contradict each other without saying so, stop and ask the layer owners. If a layer loosens a
   floor, or a waiver names a floor, stop. If the release or a layer folder is missing, cannot be read or has a
   different version from the profile, stop and name the layer and the folder.

The result is the **resolved standards** file, written once at the start of each run to
`.harness/runs/<run-id>/rules.md`, with one section per stack. For each rule that applies, in layer order, it lists
the ID, layer, kind, the ID it changed and any waiver, plus a fingerprint (hash) of every file it read. It also
lists each decision point with its option and where the option came from (a binding rule's ID, "profile decisions"
or "default"), each waiver with its status (applied, expired, or replaced by the rule that applies in its place),
and each rule that no longer applies with what replaced it (a rule ID or "profile decisions"). It holds no rule
text, so it is not a copy. Every role in the run reads this file, and each claim and verdict records the hash of
this file. A run writes it once: if the run's `rules.md` already exists and a new resolve gives different bytes, an
input changed during the run, and the run stops.
