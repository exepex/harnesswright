# CORE-CATALOG · The set of skills

Principles layer, area `CATALOG`. These rules govern the whole set of skills that one repository lists,
not any single skill. Rules for a single skill are area `SKILL` ([skill.md](skill.md)).

All text below is written new. Each Source names where the idea came from.

### CORE-CATALOG-01 · All descriptions together fit a budget

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** The descriptions of all skills that one repository lists together stay under 15,000 characters, about
  4,000 tokens. Before a new skill would exceed the budget, descriptions are shortened or skills merged.
- **Why:** Note. Hosts load every description on every task, and some cut the list above a limit. The reference host
  keeps 2% of the context window, about 16,000 characters on a 200,000-token window; the budget sits just under
  it. Past it, skills are missed.
- **Check:** Add up the length of every listed description. Is it under the budget? If a new skill would exceed it,
  were descriptions shortened or skills merged first?
- **Good:** 20 skills averaging 600 characters: 12,000 characters in all.
- **Bad:** 30 skills averaging 600 characters: 18,000 characters, and a new one added on top.
- **Eval:** a repository whose descriptions exceed the budget once a new skill is added, which the skill judge must
  flag.
- **Tool:** a script that sums the `description` fields of every listed skill
- **Source:**
  - `anthropics/claude-code@964d695 CHANGELOG.md` (all rights reserved; idea only: the 2% skill budget)
  - own
