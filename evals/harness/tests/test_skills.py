"""Skills: frontmatter is read from one stated subset or refused, and folders are checked before they are copied."""

import shutil
import unittest

from helpers import TempCase

import cases
import skills


class Frontmatter(TempCase):
    def test_the_subset_is_read(self):
        self.assertEqual(skills.frontmatter("---\nname: a\ndescription: b c\n---\nbody")["description"], "b c")
        folded = ("---\nname: demo\ndescription: >\n  Writes demos.\n\n  Use for demos.\nlicense: MIT\n"
                  "metadata:\n  source: x\n---\n# Demo\n")
        self.assertEqual(skills.frontmatter(folded), {"name": "demo", "description": "Writes demos. Use for demos.",
                                                      "license": "MIT", "metadata": ["source: x"]})
        self.assertEqual(skills.frontmatter('---\nname: "a"\ndescription: \'b: c\'\n---\n')["description"], "b: c")
        self.assertEqual(skills.frontmatter("---\nname: 'it''s'\n---\n")["name"], "it's")

    def test_the_real_skills_are_read(self):
        for folder in sorted((cases.REPO / "skills").iterdir()):
            with self.subTest(skill=folder.name):
                _, meta = skills.skill_files(folder, folder.name)
                self.assertGreater(len(meta["description"].split()), 20)

    def test_anything_outside_the_subset_is_refused(self):
        for text, reason in (("---\nname: a\ndescription: Writes demos\n  and more.\n---\n", "one line"),
                             ("---\nname: a\ndescription: x\n", "no closing"),
                             ("name: a\n", "first line"),
                             ("---\nname: a\n- item\n---\n", "not a `key: value`"),
                             ("---\nname: 'a\n---\n", "unclosed")):
            with self.subTest(text=text), self.assertRaisesRegex(cases.CaseError, reason):
                skills.frontmatter(text)

    def test_the_name_is_a_name_and_the_expected_one(self):
        folder = self.skill()
        _, meta = skills.skill_files(folder, "haiku-writer")
        self.assertEqual(meta["name"], "haiku-writer")
        with self.assertRaisesRegex(cases.CaseError, "must be 'note-taker'"):
            skills.skill_files(folder, "note-taker")
        (folder / "SKILL.md").write_text("---\nname: ../../../escape\ndescription: x\n---\n")
        with self.assertRaisesRegex(cases.CaseError, "must be a skill name"):
            skills.skill_files(folder)


class Structure(TempCase):
    def test_git_folders_and_links_that_leave_the_folder_are_found(self):
        world = self.tmp / "world"
        (world / "sub" / ".git").mkdir(parents=True)
        (world / "inside").symlink_to("sub")
        (world / "absolute").symlink_to("/etc")
        (world / "sub" / "out").symlink_to("../../elsewhere")
        found = skills.structure(world)
        self.assertEqual(len(found), 3)
        self.assertTrue(any("sub/.git" in p for p in found))
        self.assertTrue(any("absolute" in p and "absolute symlink" in p for p in found))
        self.assertTrue(any("sub/out" in p and "outside" in p for p in found))

    def test_a_link_back_in_through_the_folder_name_is_outside(self):
        world = self.tmp / "world"
        (world / "sub").mkdir(parents=True)
        (world / "README.md").write_text("x\n")
        (world / "sub" / "back").symlink_to("../../world/README.md")
        self.assertTrue(any("outside" in p for p in skills.structure(world)))
        copy = self.tmp / "copy"
        shutil.copytree(world, copy, symlinks=True)
        self.assertFalse((copy / "sub" / "back").resolve().is_relative_to(copy.resolve()))


if __name__ == "__main__":
    unittest.main()
