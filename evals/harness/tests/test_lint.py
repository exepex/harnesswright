"""World lint: a case whose world or prompt is unsound is rejected before any run."""

import unittest

from helpers import SKILL_MD, TempCase

import cases
import lint
import world
from test_world import Adapter

OWN_TEXT = "Count the syllables of every line twice before you answer, five then seven then five."


class LintFaults(TempCase):
    def problems(self, files, data=None, upstream=None):
        skills = self.skill().parent
        case = self.case(files, data)
        arm = world.build(case, Adapter, self.tmp / f"arm-{len(list(self.tmp.iterdir()))}", False, skills)
        return lint.lint(case, arm.path, skills / "haiku-writer", upstream)

    def test_a_clean_case_passes(self):
        self.assertEqual(self.problems({"README.md": "A notes app with tags and search.\n"}), [])

    def test_hf04_skill_in_world_or_prompt(self):
        planted = {
            "name in world": ({"README.md": "Try the haiku-writer helper.\n"}, None),
            "path in world": ({"notes.md": "See skills/haiku-writer for poems.\n"}, None),
            "name in prompt": ({"README.md": "x\n"}, {"prompt": "Use haiku-writer to write a poem."}),
            "own text in world": ({"STYLE.md": f"House style: {OWN_TEXT}\n"}, None),
        }
        for label, (files, data) in planted.items():
            with self.subTest(label):
                self.assertNotEqual(self.problems(files, data), [])

    def test_text_shared_with_copied_docs_upstream_or_prompt_is_the_projects(self):
        source = cases.REPO / "LICENSE"
        copy = {"world": "STYLE.md", "source": "LICENSE", "source_sha256": cases.sha256_file(source)}
        self.assertEqual(self.problems({"STYLE.md": f"{OWN_TEXT}\n"}, {"copies": [copy]}), [])
        upstream = self.tmp / "upstream"
        upstream.mkdir()
        (upstream / "SKILL.md").write_text(OWN_TEXT)
        self.assertEqual(self.problems({"STYLE.md": f"{OWN_TEXT}\n"}, upstream=upstream), [])

    def test_hf05_eval_file_and_test_tell(self):
        planted = {
            "eval file": {"README.md": "x\n", "evals/expected.txt": "a haiku\n"},
            "case file": {"README.md": "x\n", "case.json": "{}"},
            "test tell": {"README.md": "This fixture checks the grader.\n"},
            "expectation text": {"README.md": "The reply is a haiku of three lines about notes.\n"},
        }
        data = {"expectations": ["The reply is a haiku of three lines about notes"]}
        for label, files in planted.items():
            with self.subTest(label):
                self.assertNotEqual(self.problems(files, data), [])

    def test_a_file_may_allow_a_tell_word(self):
        files = {"docs/testing.md": "Run the fixture before each release.\n"}
        self.assertNotEqual(self.problems(files), [])
        self.assertEqual(self.problems(files, {"allow_words": {"docs/testing.md": ["fixture"]}}), [])

    def test_git_folders_outside_symlinks_and_drifted_copies(self):
        self.assertNotEqual(self.problems({"README.md": "x\n", ".git/HEAD": "ref: x\n"}), [])
        case = self.case({"README.md": "x\n"}, name="link")
        (case.world / "secrets").symlink_to("/etc")
        self.assertTrue(any("outside the world" in p for p in lint._structure(case.world)))
        stale = {"world": "README.md", "source": "LICENSE", "source_sha256": "0" * 64}
        self.assertTrue(any("changed since" in p for p in self.problems({"README.md": "x\n"}, {"copies": [stale]})))

    def test_fingerprint_leaves_out_shared_text(self):
        skill = self.skill("other", SKILL_MD)
        marks = lint.fingerprint(skill, [OWN_TEXT], None, "")
        self.assertFalse(marks & lint.shingles(OWN_TEXT))


if __name__ == "__main__":
    unittest.main()
