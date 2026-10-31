"""World lint: a case whose world or prompt is unsound is rejected before any run."""

import unittest

from helpers import SKILL_MD, TempCase

import cases
import lint
import world
from test_world import Adapter

OWN_TEXT = "Count the syllables of every line twice before you answer, five then seven then five."


class LintFaults(TempCase):
    def problems(self, files, data=None, upstream=None, repo=cases.REPO):
        skills = self.skill().parent
        case = self.case(files, data)
        arm = world.build(case, Adapter, self.tmp / f"arm-{len(list(self.tmp.iterdir()))}", False, skills)
        return lint.lint(case, arm.path, skills / "haiku-writer", upstream, repo)

    def source(self, text):
        """A stand-in repository holding one document, STYLE.md, and its copy entry."""
        repo = self.tmp / "repo"
        repo.mkdir(exist_ok=True)
        (repo / "STYLE.md").write_text(text)
        return repo, {"world": "STYLE.md", "source": "STYLE.md", "source_sha256": cases.sha256_file(repo / "STYLE.md")}

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
        repo, copy = self.source(f"{OWN_TEXT}\n")
        self.assertEqual(self.problems({"STYLE.md": f"{OWN_TEXT}\n"}, {"copies": [copy]}, repo=repo), [])
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
        with self.assertRaisesRegex(cases.CaseError, "a .git folder"):
            self.problems({"README.md": "x\n", ".git/HEAD": "ref: x\n"})
        case = self.case({"README.md": "x\n"}, name="link")
        (case.world / "secrets").symlink_to("../../..")
        self.assertTrue(any("outside the world" in p for p in cases.structure(case.world)))
        repo, copy = self.source("Old style.\n")
        (repo / "STYLE.md").write_text("New style.\n")
        drifted = self.problems({"STYLE.md": "Old style.\n"}, {"copies": [copy]}, repo=repo)
        self.assertTrue(any("changed since" in p for p in drifted))

    def test_a_copy_must_match_the_source_it_names(self):
        license_sha = cases.sha256_file(cases.REPO / "LICENSE")
        fake = {"world": "STYLE.md", "source": "LICENSE", "source_sha256": license_sha}
        problems = self.problems({"README.md": "x\n", "STYLE.md": SKILL_MD}, {"copies": [fake]})
        self.assertTrue(any("differs from the source" in p for p in problems))
        self.assertTrue(any("STYLE.md: holds" in p for p in problems))

    def test_an_absolute_symlink_is_refused_even_into_the_world(self):
        case = self.case({"README.md": "x\n"}, name="absolute")
        (case.world / "readme-link").symlink_to(case.world / "README.md")
        self.assertTrue(any("absolute symlink" in p for p in cases.structure(case.world)))
        self.skill()
        with self.assertRaisesRegex(cases.CaseError, "absolute symlink"):
            world.build(case, Adapter, self.tmp / "built", False, self.tmp / "skills")

    def test_a_planted_git_hook_never_runs(self):
        marker = self.tmp / "hook-ran"
        hook = f"#!/bin/sh\ntouch {marker}\n"
        case = self.case({"README.md": "x\n", ".git/hooks/pre-commit": hook},
                         {"commits": [{"message": "Start", "paths": ["README.md"]}]}, name="hooked")
        (case.world / ".git" / "hooks" / "pre-commit").chmod(0o755)
        self.skill()
        problems = lint.lint_skill("haiku-writer", Adapter, self.tmp / "cases", self.tmp / "skills")
        self.assertTrue(any("a .git folder" in p for p in problems))
        with self.assertRaises(cases.CaseError):
            world.build(case, Adapter, self.tmp / "built", False, self.tmp / "skills")
        self.assertFalse(marker.exists())

    def test_fingerprint_leaves_out_shared_text(self):
        skill = self.skill("other", SKILL_MD)
        marks = lint.fingerprint(skill, [OWN_TEXT], None, "")
        self.assertFalse(marks & lint.shingles(OWN_TEXT))


if __name__ == "__main__":
    unittest.main()
