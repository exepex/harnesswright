"""Skills: frontmatter is read from one stated subset or refused, and folders are checked before they are copied."""

import os
import shutil
import unittest

from helpers import TempCase

import cases
import skills


class Frontmatter(TempCase):
    def test_the_subset_is_read(self):
        self.assertEqual(skills.frontmatter("---\nname: a\ndescription: b c\n---\nbody")["description"], "b c")
        folded = ("---\nname: demo\ndescription: >\n  Writes demos.\n\n  Use for demos.\n  ---\nlicense: MIT\n"
                  "metadata:\n  source: x\n  sourcing: adapted\n---\n# Demo\n")
        self.assertEqual(skills.frontmatter(folded), {"name": "demo", "description": "Writes demos. Use for demos. ---",
                                                      "license": "MIT",
                                                      "metadata": {"source": "x", "sourcing": "adapted"}})
        self.assertEqual(skills.frontmatter('---\nname: "a"\ndescription: \'b: c\'\n---\n')["description"], "b: c")
        self.assertEqual(skills.frontmatter("---\nname: 'it''s'\n---\n")["name"], "it's")

    def test_the_real_skills_are_read(self):
        for folder in sorted((cases.REPO / "skills").iterdir()):
            with self.subTest(skill=folder.name):
                _, meta = skills.skill_files(folder, folder.name)
                self.assertGreater(len(meta["description"].split()), 20)
                self.assertIsInstance(meta["metadata"], dict)

    def test_anything_outside_the_subset_is_refused(self):
        refused = {
            "---\nname: a\ndescription: Writes demos\n  and more.\n---\n": "indented line",
            "---\nname: a\ndescription:\n  Writes demos.\n---\n": "is not plain",
            "---\nname: a\ndescription: x\n": "no closing",
            "name: a\n": "first line",
            " ---\nname: a\n---\n": "first line",
            "---\nname: a\n- item\n---\n": "not a field",
            "---\nname: a\nallowed-tools: Bash\n---\n": "not a field",
            "---\nname: 'a\n---\n": "not plain",
            "---\nname: a\nname: b\n---\n": "appears twice",
            "---\nname: a\ndescription: x # note\n---\n": "not plain",
            "---\nname: a\ndescription: [a, b]\n---\n": "not plain",
            "---\nname: a\ndescription: a: b\n---\n": "not plain",
            "---\nmetadata: x\n---\n": "holds indented",
            "---\nmetadata:\n  a: [1]\n---\n": "not plain",
            "---\nmetadata:\n  a: 1\n  a: 2\n---\n": "appears twice",
            "---\nmetadata:\n    deep: x\n---\n": "indented line",
            "---\nname: a\ndescription: Use when:\n---\n": "not plain",
            "---\nname: a\ndescription: x\t# note\n---\n": "not plain",
            "---\nname: a\ndescription: Writes demos.\u2028---\nx\n---\n": "line-break",
            "---\nname: a\ndescription: Writes\x0cdemos.\n---\n": "line-break",
        }
        for text, reason in refused.items():
            with self.subTest(text=text), self.assertRaisesRegex(cases.CaseError, reason):
                skills.frontmatter(text)

    def test_the_name_is_a_name_and_the_expected_one(self):
        folder = self.skill()
        _, meta = skills.skill_files(folder, "haiku-writer")
        self.assertEqual(meta["name"], "haiku-writer")
        with self.assertRaisesRegex(cases.CaseError, "must be 'note-taker'"):
            skills.skill_files(folder, "note-taker")
        (folder / "SKILL.md").write_text("---\nname: '../../../escape'\ndescription: x\n---\n")
        with self.assertRaisesRegex(cases.CaseError, "must be a skill name"):
            skills.skill_files(folder)

    def test_a_skill_folder_holds_no_links(self):
        folder = self.skill()
        (folder / "guide.md").symlink_to("SKILL.md")
        with self.assertRaisesRegex(cases.CaseError, "a link"):
            skills.skill_files(folder)


class Structure(TempCase):
    def world(self):
        world = self.tmp / "world"
        (world / "sub").mkdir(parents=True)
        (world / "README.md").write_text("x\n")
        return world

    def test_links_inside_through_real_folders_are_allowed(self):
        world = self.world()
        (world / "sub" / "readme").symlink_to("../README.md")
        (world / "docs").symlink_to("sub")
        self.assertEqual(skills.structure(world), [])

    def test_everything_else_is_found(self):
        world = self.world()
        (world / "sub" / ".git").mkdir()
        (world / "absolute").symlink_to("/etc")
        (world / "sub" / "out").symlink_to("../../elsewhere")
        (world / "missing").symlink_to("nothing")
        (world / "c").symlink_to("sub")
        (world / "a").symlink_to("c/..")
        (world / "chain").symlink_to("c")
        (world / "dot").symlink_to("README.md/.")
        (world / "slash").symlink_to("sub/")
        (world / "sub" / "alias").symlink_to("..")
        (world / "escape").symlink_to("sub/alias/../README.md")
        os.mkfifo(world / "pipe")
        self.assertIn("pipe", " ".join(skills.structure(world)))
        (world / "pipe").unlink()
        found = " ".join(skills.structure(world))
        for path in ("sub/.git", "absolute", "sub/out", "missing", "a:", "chain", "escape", "dot", "slash"):
            with self.subTest(path=path):
                self.assertIn(path, found)
        self.assertNotIn("c:", found)

    def test_a_link_back_in_through_the_folder_name_is_refused(self):
        world = self.world()
        (world / "sub" / "back").symlink_to("../../world/README.md")
        self.assertTrue(skills.structure(world))
        copy = self.tmp / "copy"
        shutil.copytree(world, copy, symlinks=True)
        self.assertFalse((copy / "sub" / "back").resolve().is_relative_to(copy.resolve()))


if __name__ == "__main__":
    unittest.main()
