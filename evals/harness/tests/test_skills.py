"""Skills: frontmatter is read from one stated subset or refused, and folders are checked before they are copied."""

import os
import shutil
import subprocess
import unittest

from helpers import TempCase

import cases
import skills


class Frontmatter(TempCase):
    def test_the_subset_is_read(self):
        text = ("---\nname: demo\ndescription: Writes demos, with file:line and it's (fine).\n\nlicense: MIT\n"
                "metadata:\n  source: owner/repo@abc skills/x\n  source-licence: MIT\n---\n# Demo\n")
        self.assertEqual(skills.frontmatter(text), {"name": "demo",
                                                    "description": "Writes demos, with file:line and it's (fine).",
                                                    "license": "MIT",
                                                    "metadata": {"source": "owner/repo@abc skills/x",
                                                                 "source-licence": "MIT"}})

    def test_the_real_skills_are_read(self):
        for folder in sorted((cases.REPO / "skills").iterdir()):
            with self.subTest(skill=folder.name):
                _, meta = skills.skill_files(folder, folder.name)
                self.assertGreater(len(meta["description"].split()), 20)
                self.assertIsInstance(meta["metadata"], dict)

    def test_anything_outside_the_subset_is_refused(self):
        refused = {
            "---\nname: a\ndescription: Writes demos\n  and more.\n---\n": "not `  key: value`",
            "---\nname: a\ndescription:\n  Writes demos.\n---\n": "is not plain",
            "---\nname: a\ndescription: x\n": "no closing",
            "name: a\n": "first line",
            " ---\nname: a\n---\n": "first line",
            "---\nname: a\n- item\n---\n": "not a field",
            "---\nname: a\nallowed-tools: Bash\n---\n": "not a field",
            "---\nname: 'a\n---\n": "not plain",
            "---\nname: 'a'\n---\n": "not plain",
            '---\nname: "a"\n---\n': "not plain",
            "---\nname: a \n---\n": "not plain",
            "---\nname: a\ndescription: >\n  Writes demos.\n---\n": "not plain",
            "---\nname: a\ndescription: |\n  Writes demos.\n---\n": "not plain",
            "---\nmetadata:\n  count: '123'\n---\n": "not plain",
            "---\nmetadata:\n  true: x\n---\n": "not `  key: value`",
            "---\nmetadata:\n  TRUE: x\n---\n": "not `  key: value`",
            "---\nmetadata:\n  no: x\n---\n": "not `  key: value`",
            "---\nmetadata:\n  a: \n---\n": "not plain",
            "---\nname: a\nname: b\n---\n": "appears twice",
            "---\nname: a\ndescription: x # note\n---\n": "not plain",
            "---\nname: a\ndescription: [a, b]\n---\n": "not plain",
            "---\nname: a\ndescription: a: b\n---\n": "not plain",
            "---\nmetadata: x\n---\n": "holds indented",
            "---\nname: a\n  b: c\n---\n": "not `  key: value`",
            "---\nmetadata:\n  a: [1]\n---\n": "not plain",
            "---\nmetadata:\n  a: x\n  a: y\n---\n": "appears twice",
            "---\nmetadata:\n    deep: x\n---\n": "not `  key: value`",
            "---\nname: a\ndescription: Use when:\n---\n": "not plain",
            "---\nname: a\ndescription: null\n---\n": "not plain",
            "---\nname: a\nmetadata:\n  enabled: true\n---\n": "not plain",
            "---\nname: a\nmetadata:\n  count: 123\n---\n": "not plain",
            "---\nname: a\nmetadata:\n  when: 2026-10-31\n---\n": "not plain",
            "---\nname: a\ndescription: x\t# note\n---\n": "line-break",
            "---\nname: a\n\t\ndescription: x\n---\n": "line-break",
            "---\nname: a\nmetadata:\n---\n": "no `  key: value`",
            "---\nmetadata:\n\nname: a\n---\n": "no `  key: value`",
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
        (folder / "SKILL.md").write_text("---\nname: a/../../escape\ndescription: x\n---\n")
        with self.assertRaisesRegex(cases.CaseError, "must be a skill name"):
            skills.skill_files(folder)

    def test_a_skill_is_the_regular_files_git_tracks(self):
        folder = self.skill()
        (folder / ".venv").mkdir()
        (folder / ".venv" / "python").symlink_to("/usr/bin/python3")
        (self.tmp / "skills" / "draft").mkdir()
        (self.tmp / "skills" / "draft" / "SKILL.md").write_text("---\nname: draft\ndescription: x\n---\n")
        files, _ = skills.skill_files(folder, "haiku-writer")
        self.assertEqual(list(files), ["SKILL.md"])
        self.assertEqual(skills.skill_names(self.tmp / "skills"), ["haiku-writer"])
        (folder / "real").mkdir()
        (folder / "real" / "ref.md").write_text("x\n")
        (folder / "docs").symlink_to("real")
        (folder / "guide.md").symlink_to("SKILL.md")
        git = lambda *args: subprocess.run(["git", *args], cwd=folder, check=True, capture_output=True)
        for rel in ("guide.md", "docs/ref.md"):
            # The index says the path is a file, at the path from the top of the repository.
            blob = git("hash-object", "-w", "SKILL.md").stdout.decode().strip()
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},haiku-writer/{rel}")
            with self.subTest(rel=rel), self.assertRaisesRegex(cases.CaseError, f"{rel} .*not a regular file"):
                skills.skill_files(folder)
            git("update-index", "--force-remove", rel)
        git("add", "real/ref.md")
        (folder / "real" / "ref.md").unlink()
        with self.assertRaisesRegex(cases.CaseError, "real/ref.md is tracked by git but cannot be read"):
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
        (world / "my notes.md").write_text("x\n")
        (world / "café").mkdir()
        os.mkfifo(world / "pipe")
        self.assertIn("pipe", " ".join(skills.structure(world)))
        (world / "pipe").unlink()
        found = " ".join(skills.structure(world))
        for path in ("sub/.git", "absolute", "sub/out", "missing", "a:", "chain", "escape", "dot", "slash",
                     "my notes.md: a path must be", "café: a path must be"):
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


class Release(TempCase):
    """A skill the release build generates is read like any other, and the release wins over a same-named skill."""

    def test_the_release_build_frontmatter_is_read(self):
        folder = cases.REPO / "v2" / "build" / "tests" / "golden" / "expected" / "golden-skill"
        _, meta = skills.skill_files(folder, "golden-skill")
        self.assertEqual(meta["metadata"]["rulebook-version"], "0.3.1")
        self.assertTrue(meta["metadata"]["copied-ids"].startswith("CORE-WORK-01, "))

    def test_only_a_plain_inside_may_be_quoted_and_only_in_metadata(self):
        read = skills.frontmatter('---\nname: a\nmetadata:\n  ids: "A-1, B-2"\n  size: "12"\n---\n')
        self.assertEqual(read["metadata"], {"ids": "A-1, B-2", "size": "12"})
        for text in ('---\nmetadata:\n  a: "x\\\\y"\n---\n', '---\nmetadata:\n  a: "x"y"\n---\n',
                     '---\nmetadata:\n  a: "x\n---\n', '---\ndescription: "x"\n---\n'):
            with self.subTest(text=text), self.assertRaisesRegex(cases.CaseError, "not plain"):
                skills.frontmatter(text)

    def write(self, rel, text):
        (self.tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / rel).write_text(text)

    def test_folders_lists_skills_and_the_release_wins(self):
        for name in ("old", "kept"):
            self.write(f"skills/{name}/SKILL.md", f"---\nname: {name}\n---\n")
        self.track(self.tmp)
        self.assertEqual(skills.folders(self.tmp), {"kept": self.tmp / "skills" / "kept",
                                                    "old": self.tmp / "skills" / "old"})
        self.write("release/manifest.json", '{"rulebook-version": "0.1.0", "skills": {"old": {}, "new": {}}}')
        self.track(self.tmp)
        self.assertEqual(skills.folders(self.tmp), {"kept": self.tmp / "skills" / "kept",
                                                    "new": self.tmp / "release" / "new",
                                                    "old": self.tmp / "release" / "old"})
        self.assertEqual(skills.library(self.tmp / "skills"), {"kept": self.tmp / "skills" / "kept",
                                                               "old": self.tmp / "skills" / "old"})

    def test_a_manifest_without_a_list_of_names_is_refused(self):
        for text in ("[]", '{"skills": {"../x": {}}}', "{", '{"skills": "abc"}'):
            with self.subTest(text=text):
                self.write("release/manifest.json", text)
                self.track(self.tmp)
                with self.assertRaisesRegex(cases.CaseError, "release/manifest.json"):
                    skills.folders(self.tmp)


if __name__ == "__main__":
    unittest.main()
