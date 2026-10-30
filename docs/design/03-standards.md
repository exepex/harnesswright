# 03 · Standards and rules

Standards describe what good work looks like: code, tests, documentation, configuration and security. They are
written in layers, so that generic principles are written once and local conventions can still win.

## The five layers

| Layer | ID prefix | Holds | Lives in |
|---|---|---|---|
| Core | `CORE` | Principles every language shares, the safety floors, and the decision points | `standards/core/` |
| Language | `JAVA`, `PY`, `GO`, `RUST`, `GROOVY`, `TS`, … | Idioms, decision-point defaults and the toolchain for one language or platform | `standards/languages/<language>/` |
| Organisation | `ORG-<name>` | Choices one organisation makes for all its teams | `standards/org/<name>/` (empty for now) |
| Team | `TEAM-<name>` | Choices one team makes | `standards/team/<name>/` (empty for now) |
| Repository | `REPO` | Facts and choices of one codebase | `.harness/standards/` in that repository |

A platform such as Spring Boot is a sub-profile of a language (`JAVA-SPRING`). It sits between the language and
the organisation, and extends the language.

The repository profile names the layers that apply, in order. See [07 · Repository profile](07-repo-profile.md).

## Precedence

1. The more specific layer wins: repository over team, team over organisation, organisation over language,
   language over core.
2. A **floor** can never be loosened by a lower layer. A lower layer may tighten it.
3. A rule that changes another rule must say so (`overrides`, `binds` or `tightens`), so every change is
   visible. A silent contradiction is a defect in the standards.
4. If a lower layer tries to loosen a floor, agents stop and ask the owner. They do not choose a side.

## Four kinds of rule

Every rule has exactly one kind. The kind decides where it may live and whether it may be overridden.

| Kind | Meaning | Example | Where | Overridable |
|---|---|---|---|---|
| **Principle** | An outcome every codebase should reach | "A unit has one reason to change" | Core | Only with a stated reason |
| **Floor** | A safety minimum that is never traded away | "No secret appears in code, configuration, logs or tests" | Core, or tightened lower | Never loosened |
| **Idiom** | How a principle is done well in one language | "Go: return errors as values; wrap them with context" | Language | By organisation, team or repository |
| **Choice** | One of several valid options a team picks | "Generate boilerplate with Lombok" | Binds a decision point, in any layer below core | Yes |

The most common mistake in generic standards is a choice disguised as a principle. "Use Lombok" is a choice;
"Do not hand-write boilerplate that a language feature or a generator can produce" is a principle.

## Decision points

The core names each place where reasonable teams choose differently, gives it a default, and lets lower layers
bind it. A decision point has an ID of the form `CORE-DP-<NAME>`.

| Decision point | Core default | Example bindings |
|---|---|---|
| `CORE-DP-BOILERPLATE` | Use the language's own feature (records, data classes) | Lombok · explicit hand-written accessors |
| `CORE-DP-MAPPING` | Plain mapping functions in a dedicated mapper unit | MapStruct · manual mappers |
| `CORE-DP-CONSTRUCTION` | Constructor; builder when there are several optional fields | Builder for all public types · constructor only |
| `CORE-DP-INJECTION` | Constructor injection | (fixed in most teams) |
| `CORE-DP-ERRORS` | The language's idiomatic error model | Checked exceptions · result types |
| `CORE-DP-TEST-STACK` | The language profile's default test tools | JUnit 5 + AssertJ · pytest |
| `CORE-DP-NULLS` | Make absence explicit in the type | `Optional` · nullability annotations |

The list will grow as the harvest finds more. Each new point needs at least two teams that really choose
differently.

## Rule format

This format is for standards only. Rules for working on harnesswright itself (`HW-AG`, `HW-PORT`) are a separate
scope, defined in `AGENTS.md` and [10 · Skills](10-skills.md).

Each standards file covers one area and holds several rules. A rule looks like this:

```markdown
### CORE-TEST-03 · A test name states the scenario and the expected outcome

- **Kind:** principle
- **Applies to:** implementer, tester, reviewer, judge
- **Rule:** Name each test after the situation it sets up and the result it expects, in plain words.
- **Why:** A failing test should tell the reader what broke without opening the test body.
- **Check:** Review question: "Can I tell from the name alone what failed?"
- **Good:** `rejectsOrderWhenStockIsInsufficient`
- **Bad:** `testOrder2`, `shouldWork`
- **Source:** own
```

For a rule in a lower layer, add one relation line:

- `**Overrides:** CORE-…`: replaces a principle or idiom, with a reason.
- `**Binds:** CORE-DP-…`: chooses an option for a decision point.
- `**Tightens:** CORE-…`: makes a floor stricter.

Optional fields are **Tool** (a check that proves the rule mechanically) and **Exceptions** (when the rule does not
apply). `Source` records where the idea came from: `own`, or `<repository>@<commit> <path> (<licence>)`.

## Rule IDs

`<LAYER>-<AREA>-<NN>`, for example `CORE-NAME-04`, `JAVA-TEST-02` or `REPO-CONF-01`. An ID never changes and is
never reused. A retired rule keeps its ID and is marked `retired` with a pointer to its replacement.

Areas, one core file each:

| Area | Covers |
|---|---|
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

## Language-neutral wording in the core

Core rules use neutral words, so every language can apply them:

| Core word | Means | Java | Go | Python |
|---|---|---|---|---|
| unit | the smallest named piece of design | class | package or type | module or class |
| function | named behaviour | method | function or method | function or method |
| interface | a contract other code depends on | interface | interface | protocol |
| API documentation | the reader-facing description of a unit | Javadoc | doc comment | docstring |

Each language profile includes this mapping, so no core rule needs Java words.

## When a repository has written nothing down

1. Read the profile and the repository layer, if they exist.
2. If not, infer conventions from the existing code. New code should look like the code next to it. If most
   classes use Lombok, use Lombok.
3. Write what was inferred to `.harness/standards/` as proposed rules, marked `inferred`.
4. A human confirms them once. From then on they are ordinary repository rules.

## Resolving the rules for a repository

The resolved standards are the core rules, then each listed layer applied in order, with every override, binding
and tightening recorded. At first, agents resolve them by reading the layers in order, guided by a skill. If that
proves slow or error-prone, a small resolver script can be added later. That needs the owner's approval.
