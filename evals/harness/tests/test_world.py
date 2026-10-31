"""Worlds: case checks, both arms built from one world, and the hash proof that they differ only by the skill."""

import json
import unittest

from helpers import TempCase

import cases
import world

INDEX = {"file": "AGENTS.md", "after": "| Skill | Path | Use when |",
         "row": "| {name} | [{path}]({path}) | {description} |"}
AGENTS = "# Rules\n\n## Skills\n\n| Skill | Path | Use when |\n|---|---|---|\n\nEnd.\n"


class Adapter:
    """Only what the world builder needs from an adapter."""

    @staticmethod
    def skill_dir(root, name):
        return root / ".host" / "skills" / name


class CaseChecks(TempCase):
    def test_a_trigger_case_needs_its_split_and_answer(self):
        with self.assertRaisesRegex(cases.CaseError, "should_trigger.*split"):
            self.case({"README.md": "x"}, {"kind": "trigger"})

    def test_unknown_fields_and_paths_outside_the_world_are_refused(self):
        with self.assertRaisesRegex(cases.CaseError, "unknown fields.*skill_path"):
            self.case({"README.md": "x"}, {"colour": 1, "skill_path": "../out"})

    def test_frontmatter(self):
        self.assertEqual(cases.frontmatter("---\nname: a\ndescription: b c\n---\nbody")["description"], "b c")


class Arms(TempCase):
    def build_pair(self, data=None, files=None):
        skills = self.skill().parent
        case = self.case(files or {"README.md": "Notes app.\n", "AGENTS.md": AGENTS}, dict({"index": INDEX}, **(data or {})))
        base = world.build(case, Adapter, self.tmp / "base", False, skills)
        with_arm = world.build(case, Adapter, self.tmp / "with", True, skills)
        return case, base, with_arm

    def test_the_with_skill_arm_is_the_world_plus_the_skill(self):
        case, base, with_arm = self.build_pair()
        proof = world.prove(base, with_arm)
        self.assertEqual(proof["changed"], ["AGENTS.md"])
        self.assertEqual(proof["added"], [".host/skills/haiku-writer/SKILL.md", "skills/haiku-writer/SKILL.md"])
        self.assertFalse((base.path / "skills").exists())
        self.assertEqual((base.path / "AGENTS.md").read_text(), AGENTS)
        rows = [line for line in (with_arm.path / "AGENTS.md").read_text().split("\n") if "haiku-writer" in line]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].startswith("| haiku-writer | [skills/haiku-writer/SKILL.md]"))

    def test_the_row_goes_at_the_end_of_its_table(self):
        path = self.tmp / "AGENTS.md"
        path.write_text("| Skill | Path | Use when |\n|---|---|---|\n| a | b | c |\n\nAfter.\n")
        world.add_row(path, "| Skill | Path | Use when |", "| new | row | here |")
        self.assertEqual(path.read_text().split("\n")[3], "| new | row | here |")

    def test_history_is_the_same_in_both_arms(self):
        _, base, with_arm = self.build_pair({"commits": [{"message": "Start", "paths": ["README.md"]}]})
        self.assertIsNotNone(base.head)
        self.assertEqual(base.head, with_arm.head)

    def test_siblings_are_installed_in_both_arms(self):
        self.skill("note-taker")
        _, base, with_arm = self.build_pair({"siblings": ["note-taker"]})
        self.assertTrue((base.path / "skills/note-taker/SKILL.md").is_file())
        self.assertTrue((with_arm.path / "skills/note-taker/SKILL.md").is_file())
        world.prove(base, with_arm)


class WorldFaults(TempCase):
    def test_hf09_arms_differ_beyond_the_skill(self):
        skills = self.skill().parent
        case = self.case({"README.md": "Notes app.\n", "AGENTS.md": AGENTS}, {"index": INDEX})
        base = world.build(case, Adapter, self.tmp / "base", False, skills)
        for tamper in ("stray", "edit", "row"):
            target = self.tmp / f"with-{tamper}"
            with_arm = world.build(case, Adapter, target, True, skills)
            if tamper == "stray":
                (target / "hint.md").write_text("The skill is under skills/.\n")
            elif tamper == "edit":
                (target / "README.md").write_text("Notes app. Use the haiku skill.\n")
            else:
                agents = target / "AGENTS.md"
                agents.write_text(agents.read_text() + "\nAlways write haiku.\n")
            tampered = world.Arm(target, "with_skill", with_arm.overlay, with_arm.head)
            with self.subTest(tamper=tamper), self.assertRaises(cases.CaseError):
                world.prove(base, tampered)


if __name__ == "__main__":
    unittest.main()
