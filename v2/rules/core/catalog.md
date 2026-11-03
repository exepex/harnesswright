# CORE-CATALOG · The set of skills and roles

Principles layer, area `CATALOG`. These rules govern the whole set of skills and roles that one repository lists,
not any single skill. Rules for a single skill are area `SKILL` ([skill.md](skill.md)).

All text below is written new. Each Source names where the idea came from.

### CORE-CATALOG-01 · All descriptions together fit a budget

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** skill designer, skill judge
- **Rule:** The descriptions of all skills and roles that one repository lists together stay under 40,000
  characters, about 10,000 tokens. A new skill that would pass the budget shortens descriptions or merges skills
  first.
- **Why:** Hosts load every description on every task, and some warn or cut the list above a limit. Past it, skills
  are missed and every task pays for the text.
- **Check:** Add up the length of every listed description and compare it with the budget.
- **Good:** 25 skills averaging 600 characters: 15,000 characters in all.
- **Bad:** 40 skills averaging 1,000 characters: 40,000 characters, with a new one on top.
- **Eval:** a repository whose descriptions pass the budget once a new skill is added, which the skill judge must
  flag.
- **Tool:** a script that sums the `description` fields of every listed skill and role
- **Source:**
  - `anthropics/claude-plugins-official@a2e251d plugins/plugin-dev/skills/agent-development/SKILL.md`
    (Apache-2.0)
  - own
