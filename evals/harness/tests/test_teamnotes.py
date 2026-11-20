"""Team notes hold the team's rules, never harnesswright's (teamnotes.py), read through the world lint."""

import unittest

from helpers import TempCase

import cases
import lint
import teamnotes
from test_world import Adapter

RULE_LINE = next(line for line in (cases.REPO / "release" / "rules" / "core" / "work.md").read_text().splitlines()
                 if line.startswith("- **Rule:**") and len(line.split()) > 12)


class TeamNotes(TempCase):
    def problems(self, files, skill="claims-writer"):
        skills = self.skill(skill).parent
        case = self.case(files, skill=skill)
        return lint.lint_case(case, Adapter, self.tmp / f"arms-{case.id}", skills)

    def test_the_release_is_the_one_source_of_rule_ids_and_text(self):
        ids, text = teamnotes.harness_rules(cases.REPO)
        self.assertIn("CORE-WORK-07", ids)
        self.assertNotIn("CORE-WORK-99", ids)
        self.assertTrue(text)

    def test_a_team_note_naming_a_harnesswright_rule_is_refused(self):
        problems = self.problems({"README.md": "Notes app.\n", "AGENTS.md": "# Rules\n\nFollow CORE-WORK-07.\n"})
        self.assertTrue(any("names harnesswright's rule CORE-WORK-07" in p for p in problems), problems)

    def test_a_team_note_holding_harnesswright_rule_text_is_refused(self):
        problems = self.problems({"README.md": "Notes app.\n", "AGENTS.md": f"# Rules\n\n{RULE_LINE[12:]}\n"})
        self.assertTrue(any("holds harnesswright's rule text" in p for p in problems), problems)

    def test_the_harness_folder_may_name_rules_and_team_rules_pass(self):
        files = {"README.md": "Notes app.\n", "AGENTS.md": "# Rules\n\nEvery change ships with its tests.\n",
                 ".harness/profile.yaml": "waivers:\n  - rule: CORE-WORK-07\n"}
        self.assertEqual([p for p in self.problems(files) if "harnesswright's rule" in p], [])

    def test_only_a_team_skill_is_held_to_it(self):
        problems = self.problems({"README.md": "Notes app.\n", "AGENTS.md": "Follow CORE-WORK-07.\n"}, "haiku-writer")
        self.assertEqual([p for p in problems if "harnesswright's rule" in p], [])


if __name__ == "__main__":
    unittest.main()
