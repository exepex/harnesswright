"""World lint: every rule reads one list of what the run can see, and a case that fails it cannot run."""

import unittest

from helpers import SKILL_MD, TempCase

import cases
import lint
import world
from test_world import AGENTS, INDEX, Adapter

OWN_TEXT = "Count the syllables of every line twice before you answer, five then seven then five."


class Lint(TempCase):
    def problems(self, files, data=None, upstream=(), repo=cases.REPO, siblings=()):
        skills = self.skill().parent
        for name, text in dict(siblings).items():
            (self.skill(name) / "SKILL.md").write_text(text)
        case = self.case(files, data)
        arm = world.build(case, Adapter, self.tmp / f"arm-{case.id}", skills)
        return lint.lint(case, arm, skills / "haiku-writer", upstream, repo)

    def source(self, text):
        """A stand-in repository holding one document, STYLE.md, and its copy entry."""
        repo = self.tmp / "repo"
        repo.mkdir(exist_ok=True)
        (repo / "STYLE.md").write_text(text)
        return repo, {"world": "STYLE.md", "source": "STYLE.md", "source_sha256": cases.sha256_file(repo / "STYLE.md")}

    def test_a_clean_case_passes(self):
        self.assertEqual(self.problems({"README.md": "A notes app with tags and search.\n"}), [])

    def test_every_place_is_read_whatever_its_encoding_or_kind(self):
        case = self.case({"README.md": "x\n"}, {"commits": [{"message": "Start", "paths": ["README.md"]}]})
        (case.world / "notes.bin").write_bytes(b"\xff\xfe binary haiku_writer \x00")
        (case.world / "Haiku-Writer.md").write_text("x\n")
        (case.world / "link").symlink_to("Haiku-Writer.md")
        (case.world / "fixtures").mkdir()
        arm = world.build(case, Adapter, self.tmp / "arm", self.skill().parent)
        keys = {place.key for place in lint.visible(case, arm)}
        self.assertEqual(keys, {"<prompt>", "<commit 1>", "README.md", "notes.bin", "Haiku-Writer.md", "link",
                                "fixtures"})
        found = " ".join(lint.lint(case, arm, self.tmp / "skills/haiku-writer"))
        for where in ("notes.bin: names", "Haiku-Writer.md: names", "link: names", "fixtures: test-tell"):
            with self.subTest(where=where):
                self.assertIn(where, found)

    def test_the_skill_is_never_in_what_the_run_sees(self):
        planted = {
            "name in world": ({"README.md": "Try the haiku writer helper.\n"}, None),
            "path in world": ({"notes.md": "See skills/haiku-writer for poems.\n"}, None),
            "custom path": ({"notes.md": "See tools/poems.\n"}, {"skill_path": "tools/poems"}),
            "name in prompt": ({"README.md": "x\n"}, {"prompt": "Use Haiku_Writer to write a poem."}),
            "own text in world": ({"STYLE.md": f"House style: {OWN_TEXT}\n"}, None),
            "name in commit": ({"README.md": "x\n"}, {"commits": [{"message": "Add haiku-writer", "paths": []}]}),
        }
        for label, (files, data) in planted.items():
            with self.subTest(label):
                self.assertNotEqual(self.problems(files, data), [])

    def test_a_sibling_that_names_the_skill_is_found(self):
        sibling = "---\nname: note-taker\ndescription: Takes notes. Use with haiku-writer.\n---\n# Notes\n"
        problems = self.problems({"README.md": "x\n", "AGENTS.md": AGENTS},
                                 {"siblings": ["note-taker"], "index": INDEX}, siblings={"note-taker": sibling})
        self.assertTrue(any("skills/note-taker/SKILL.md: names" in p for p in problems), problems)
        self.assertTrue(any("<index rows>: names" in p for p in problems), problems)

    def test_installed_skills_may_use_test_words(self):
        sibling = "---\nname: note-taker\ndescription: Takes notes and runs evals with a fixture.\n---\n# Notes\n"
        self.assertEqual(self.problems({"README.md": "x\n", "AGENTS.md": AGENTS},
                                       {"siblings": ["note-taker"], "index": INDEX},
                                       siblings={"note-taker": sibling}), [])

    def test_text_shared_with_copies_upstream_or_prompt_is_the_projects(self):
        repo, copy = self.source(f"{OWN_TEXT}\n")
        self.assertEqual(self.problems({"STYLE.md": f"{OWN_TEXT}\n"}, {"copies": [copy]}, repo=repo), [])
        self.assertEqual(self.problems({"STYLE.md": f"{OWN_TEXT}\n"}, upstream=[OWN_TEXT]), [])
        self.assertEqual(self.problems({"README.md": "x\n"}, {"prompt": f"Write a poem. {OWN_TEXT}"}), [])

    def test_eval_files_tells_and_expectation_text_are_refused(self):
        planted = {
            "eval folder": {"README.md": "x\n", "evals/expected.txt": "a poem\n"},
            "case file": {"README.md": "x\n", "case.json": "{}"},
            "test tell": {"README.md": "This fixture checks the grader.\n"},
            "expectation text": {"README.md": "The reply is a poem of three lines about notes.\n"},
        }
        data = {"expectations": ["The reply is a poem of three lines about notes"]}
        for label, files in planted.items():
            with self.subTest(label):
                self.assertNotEqual(self.problems(files, data), [])

    def test_a_place_may_allow_a_tell_word(self):
        files = {"docs/testing.md": "Run the fixture before each release.\n"}
        self.assertNotEqual(self.problems(files), [])
        self.assertEqual(self.problems(files, {"allow_words": {"docs/testing.md": ["fixture"]}}), [])
        self.assertEqual(self.problems({"README.md": "x\n"}, {"prompt": "Write a poem for the eval.",
                                                             "allow_words": {"<prompt>": ["eval"]}}), [])

    def test_a_copy_must_be_its_source(self):
        repo, copy = self.source("Old style.\n")
        (repo / "STYLE.md").write_text("New style.\n")
        self.assertTrue(any("changed since" in p for p in self.problems({"STYLE.md": "Old style.\n"},
                                                                        {"copies": [copy]}, repo=repo)))
        fake = dict(copy, world="OTHER.md")
        problems = self.problems({"OTHER.md": SKILL_MD}, {"copies": [fake]}, repo=repo)
        self.assertTrue(any("not in the world as the regular file" in p for p in problems))
        self.assertTrue(any("OTHER.md: holds" in p for p in problems))

    def test_lint_skill_reports_an_unbuildable_case(self):
        self.skill()
        case = self.case({"README.md": "x\n"}, name="linked")
        (case.world / "out").symlink_to("../../..")
        problems = lint.lint_skill("haiku-writer", Adapter, self.tmp / "cases", self.tmp / "skills", self.tmp)
        self.assertTrue(any("unsound" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
