# 01 · Charter

## What harnesswright is

harnesswright is a reusable set of agent roles, skills and engineering standards that lets a team of AI agents
plan, build, test, review and verify software with little human guidance. It works with any repository, whatever
its language (Java, Spring Boot, Python, Go, Rust, Groovy and others) or architecture (library, microservice, web
application, batch job, command-line tool, producer or consumer).

A repository adopts it by installing the harness and adding one profile file. From then on, every agent that works
in that repository follows the same standards and the same process, without being told again.

## The problem it solves

Agents implement well, but they need to be told the same things again and again: how to name things, how to split
a class, how to write a realistic test, how to comment, how big a file may be, how to apply SOLID, KISS and DRY.
Each repository repeats those instructions in its own words. Quality then depends on which repository an agent is
in and on who wrote its instructions.

harnesswright writes those instructions once, in layers, and makes every role apply them.

## Goals

1. **Write standards once, use them everywhere.** Engineering principles live in one core. Each language, organisation,
   team and repository adds only what is specific to it.
2. **Respect local conventions.** A team's choices, such as Lombok or explicit accessors, win over generic defaults.
   Safety floors never lose.
3. **Decide by independent agreement, not by one agent.** Plans, stories and finished work are approved by panels
   of independent agents, with a veto for any blocker that is proven with evidence.
4. **Prove, don't claim.** Facts that a tool can check (tests, coverage, lint, security scans, file sizes) are checked
   by the tool, not voted on.
5. **Spend effort in proportion to risk.** A typo gets one judge; a change to a public API or security code gets the
   full pipeline.
6. **Keep the human in charge with little effort.** A human approves the plan for large changes and the final merge,
   and answers clear questions when agents cannot agree.
7. **Measure the harness itself.** Every change to a skill or standard is checked against a fixed set of tasks before
   release.
8. **Run with any frontier model.** The same skills, roles and standards work in every agent host that reads the
   Agent Skills standard, whichever frontier model it runs: Claude, GPT, Gemini, Grok, Kimi, DeepSeek, Qwen,
   Mistral, Llama and those still to come. Behaviour on each host is measured by the same evals, and each host is
   labelled verified, compatible or unsupported. See [10 · Skills](10-skills.md).
9. **Borrow before building.** Good existing skills, from vendors or the community, are adopted or adapted before
   anything is written from scratch, with their source and licence recorded.

## Non-goals

- harnesswright is not an agent runtime or a framework. It uses the agent hosts that already exist and read Agent
  Skills (`SKILL.md`), such as Claude Code and OpenAI Codex.
- It contains no business or domain logic, and no project-specific code.
- It does not replace build tools, linters, scanners or CI. It tells agents which ones to run and how to read the
  results.
- It does not grant agents access to production systems.

## Design principles for the harness itself

- **Simple first.** Build only what a real repository needs now. Empty layers stay empty until a real need appears.
- **One voice.** Every standard, role and contract uses the same words and the same formats, even when an idea was
  borrowed from elsewhere.
- **Small files.** A text file stays under 500 lines and a configuration file under 400, so a reviewer can read
  each one in a sitting. A generated release skill is bounded by size ceilings instead (CORE-TEMPLATE-02).
- **Separate what, who and when.** Standards say what good work is; roles say who does the work; process says when
  each role runs. See [02 · Architecture](02-architecture.md).
- **Least privilege.** Each role gets only the tools and access its work needs.
- **Every rule earns its place.** A rule must be specific, checkable and backed by a reason. Vague advice such as
  "write clean code" is not a rule.

## How success is measured

| Measure | Meaning |
|---|---|
| Human interventions per change | How often a person had to correct or unblock the agents. The main measure. |
| First-pass approval rate | Share of stories the judges approve without a rework round. |
| Escaped defects | Problems found after merge that the harness should have caught. |
| Cost and time per change | Tokens and wall-clock time, by risk tier. |
| Eval pass rate | Share of the harness's own test tasks that pass, per release. |

## Human gates

| Gate | When | Default |
|---|---|---|
| Plan approval | Tier 3 changes, after the plan panel approves | On |
| Merge | Every change, after the final judges pass it | On, always |
| Escalation | When a panel deadlocks, a budget runs out or a round limit is reached | On, always |
| Standards change | When the learning loop proposes a new or changed rule | On, always |

Process configuration can add gates. It cannot remove the merge, escalation or standards-change gates.
