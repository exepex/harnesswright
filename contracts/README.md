# Contracts

The templates of the files one role hands to another. [06 · Contracts](../docs/design/06-contracts.md) defines
each one; a template holds exactly its fields and sections, in its order, and nothing else.

## How to fill one

- Copy the template into the run folder, `.harness/runs/<run-id>/`, at the path below.
- Keep every field and heading. Replace each part in angle brackets. A comment after `#` lists the allowed values.
- Repeat an entry, such as `### AC-1`, once per item, numbered in order.
- Leave out a section marked `only when` when its condition does not hold, and an `optional` one the team does not
  use. Write `None.` in any other section that has nothing in it.

## Templates

| Template | Run folder path | Written by | Doc 06 section |
|---|---|---|---|
| [triage.md](triage.md) | `triage.md` | triage | Triage |
| [functional-plan.md](functional-plan.md) | `functional-plan.md` | functional planner | Functional plan |
| [technical-design.md](technical-design.md) | `design.md` | technical designer | Technical design |
| [decision-record.md](decision-record.md) | `decisions/<decision>.md` | technical designer | Decision record |
| [story.md](story.md) | `stories/<story ID>.md` | story writer, or triage for a story with no plan | Story |

`rules.md` has no template: the standards reader writes it in the format of
[03 · Standards](../docs/design/03-standards.md), "Resolving the rules for an application".
