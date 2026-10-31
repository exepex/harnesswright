"""World lint: every rule reads one list of what the run can see, and a case that fails it cannot run."""

import unittest

from helpers import SKILL_MD, TempCase

import cases
import lint
import world
from test_world import AGENTS, INDEX, Adapter

OWN_TEXT = "Count the syllables of every line twice before you answer, five then seven then five."
KIT_TEXT = "The grader opens each bundle and answers every expectation with quoted evidence from the run."


class Lint(TempCase):
    def problems(self, files, data=None, upstream=(), kit=(), repo=cases.REPO, siblings=(), case_data=()):
        skills = self.skill().parent
        for name, text in dict(siblings).items():
            (self.skill(name) / "SKILL.md").write_text(text)
        case = self.case(files, data)
        arm = world.build(case, Adapter, self.tmp / f"arm-{case.id}", skills)
        return lint.lint(case, arm, skills / "haiku-writer", upstream, kit, repo, case_data)

    def source(self, text):
        """A stand-in repository holding one document, STYLE.md, and its copy entry."""
        repo = self.tmp / "repo"
        repo.mkdir(exist_ok=True)
        (repo / "STYLE.md").write_text(text)
        return repo, {"world": "STYLE.md", "source": "STYLE.md", "source_sha256": cases.sha256_file(repo / "STYLE.md")}

    def test_a_clean_case_passes(self):
        self.assertEqual(self.problems({"README.md": "A notes app with tags and search.\n"}, kit=[KIT_TEXT]), [])

    def test_every_place_is_read_and_unreadable_text_is_refused(self):
        case = self.case({"README.md": "x\n"}, {"commits": [{"message": "Start", "paths": ["README.md"]}]})
        (case.world / "Haiku-Writer.md").write_text("x\n")
        (case.world / "link").symlink_to("Haiku-Writer.md")
        (case.world / "fixtures").mkdir()
        for name, data in {"utf16.txt": "Try haiku-writer.\n".encode("utf-16"), "zipped.gz": b"\x1f\x8b\x08\x00",
                           "nul.txt": b"haiku\x00writer\n"}.items():
            (case.world / name).write_bytes(data)
        arm = world.build(case, Adapter, self.tmp / "arm", self.skill().parent)
        keys = {place.key for place in lint.visible(case, arm)}
        self.assertEqual(keys, {"<prompt>", "<commit 1>", "README.md", "Haiku-Writer.md", "link", "fixtures",
                                "utf16.txt", "zipped.gz", "nul.txt"})
        found = " ".join(lint.lint(case, arm, self.tmp / "skills/haiku-writer"))
        for where in ("Haiku-Writer.md: names", "link: names", "fixtures: test-tell", "utf16.txt: not UTF-8",
                      "zipped.gz: not UTF-8", "nul.txt: not UTF-8"):
            with self.subTest(where=where):
                self.assertIn(where, found)

    def test_the_skill_is_never_in_what_the_run_sees(self):
        planted = {
            "name in world": ({"README.md": "Try the haiku writer helper.\n"}, None),
            "camel case": ({"app/poems.py": "class HaikuWriter:\n    pass\n"}, None),
            "plural": ({"README.md": "For haiku writers.\n"}, None),
            "next to kana": ({"README.md": "HaikuWriterを使う。请使用haiku-writer技能。\n"}, None),
            "soft hyphen": ({"README.md": "Try hai­ku-writer.\n"}, None),
            "full width": ({"README.md": "Try ｈａｉｋｕ-writer.\n"}, None),
            "path in world": ({"notes.md": "See skills/haiku-writer for poems.\n"}, None),
            "custom path": ({"notes.md": "See tools/poems.\n"}, {"skill_path": "tools/poems"}),
            "name in prompt": ({"README.md": "x\n"}, {"prompt": "Use Haiku_Writer to write a poem."}),
            "own text in world": ({"STYLE.md": f"House style: {OWN_TEXT}\n"}, None),
            "name in commit": ({"README.md": "x\n"}, {"commits": [{"message": "Add haiku-writer", "paths": []}]}),
        }
        for label, (files, data) in planted.items():
            with self.subTest(label):
                self.assertNotEqual(self.problems(files, data), [])

    def test_installed_siblings_are_checked_for_the_skill_only(self):
        files, data = {"README.md": "x\n", "AGENTS.md": AGENTS}, {"siblings": ["note-taker"], "index": INDEX}
        naming = "---\nname: note-taker\ndescription: Takes notes. Use with haiku-writer.\n---\n# Notes\n"
        problems = self.problems(files, data, siblings={"note-taker": naming})
        self.assertTrue(any("skills/note-taker/SKILL.md: names" in p for p in problems), problems)
        self.assertTrue(any("<sibling rows>: names" in p for p in problems), problems)
        shared = f"---\nname: note-taker\ndescription: Takes notes and runs evals with a fixture.\n---\n{OWN_TEXT}\n"
        self.assertEqual(self.problems(files, data, siblings={"note-taker": shared}), [])
        row = dict(INDEX, row=f"| {{name}} | {{path}} | {OWN_TEXT} |")
        problems = self.problems(dict(files, **{"README.md": f"{OWN_TEXT}\n"}), dict(data, index=row),
                                 siblings={"note-taker": shared.replace(OWN_TEXT, "Notes.")})
        self.assertTrue(any("README.md: holds" in p for p in problems), problems)

    def test_text_shared_with_copies_upstream_or_prompt_is_the_projects(self):
        repo, copy = self.source(f"{OWN_TEXT}\n")
        self.assertEqual(self.problems({"STYLE.md": f"{OWN_TEXT}\n"}, {"copies": [copy]}, repo=repo), [])
        self.assertEqual(self.problems({"STYLE.md": f"{OWN_TEXT}\n"}, upstream=[OWN_TEXT]), [])
        self.assertEqual(self.problems({"README.md": "x\n"}, {"prompt": f"Write a poem. {OWN_TEXT}"}), [])

    def test_tells_kit_text_and_expectations_are_refused_wherever_the_author_put_them(self):
        repo, copy = self.source("The evaluator reads each case.\n")
        data = {"expectations": ["The reply is a poem of three lines about notes", "Ends with one question"]}
        planted = {
            "tell stem": ({"README.md": "The evaluator compares with the goldens.\n"}, {}),
            "tell in a copy": ({"STYLE.md": "The evaluator reads each case.\n"}, {"copies": [copy]}),
            "tell in the row": ({"README.md": "x\n", "AGENTS.md": AGENTS},
                                {"index": dict(INDEX, row="| {name} | {path} | graded |")}),
            "kit text": ({"notes/how.md": f"Note: {KIT_TEXT}\n"}, {}),
            "kit text in the prompt": ({"README.md": "x\n"}, {"prompt": f"Write a poem. {KIT_TEXT}"}),
            "expectation": ({"README.md": "The reply is a poem of three lines about notes.\n"}, {}),
            "short expectation": ({"TODO.md": "Reply ends with one question.\n"}, {}),
        }
        for label, (files, extra) in planted.items():
            with self.subTest(label):
                self.assertNotEqual(self.problems(files, dict(data, **extra), kit=[KIT_TEXT], repo=repo), [])

    def test_project_text_is_never_counted_against_the_case(self):
        data = {"prompt": "Write a poem of three lines about notes.",
                "expectations": ["The reply is a poem of three lines about notes", "Uses tags", "!!!", "回答包含三行诗"]}
        self.assertEqual(self.problems({"README.md": "This app uses tags.\n", "src/cases/list.py": "x = 1\n"},
                                       data), [])
        repo, copy = self.source("Every file ends with a newline.\n")
        self.assertEqual(self.problems({"STYLE.md": "Every file ends with a newline.\n", "NOTES.md": "Every file "
                                        "ends with a newline.\n"}, {"copies": [copy], "expectations": [
                                            "Every file ends with a newline"]}, repo=repo), [])

    def test_a_place_may_allow_a_tell_word(self):
        files = {"docs/testing.md": "Run the fixtures before each release.\n"}
        self.assertNotEqual(self.problems(files), [])
        self.assertEqual(self.problems(files, {"allow_words": {"docs/testing.md": ["fixtures"]}}), [])
        files = {"README.md": "Evaluation measures search quality. The evaluator scores your response.\n"}
        self.assertEqual([p.split(": ", 1)[1] for p in self.problems(files, {"allow_words": {
            "README.md": ["evaluation"]}})], ["README.md: test-tell word 'evaluator'"])
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

    def test_eval_text_is_what_the_evals_say_about_skills(self):
        evals = self.tmp / "repo" / "evals"
        paths = ("harness/README.md", "runner/core.py", "skills/x/checks/c.py", "skills/x/tasks.json",
                 "skills/x/cases/a/case.json", "skills/x/cases/a/world/README.md", "skills/x/files/old/README.md",
                 "skills/x/upstream/SKILL.md", "skills/x/answers/world/key.md", "faults/f.md", "results/r.json",
                 "goldens/g.md")
        for path in paths:
            (evals / path).parent.mkdir(parents=True, exist_ok=True)
            (evals / path).write_text(path)
        (evals / "skills/x/checks/c.py").write_text("import os\nassert f'poem {n}' in out  # one poem\n")
        measuring, data = lint.eval_texts(self.tmp / "repo")
        self.assertEqual([" ".join(lint.words(t)) for t in measuring],
                         ["faults f md", "goldens g md", "results r json", "skills x answers world key md", "poem one poem"])
        self.assertEqual([text for _, text in data], ["skills/x/cases/a/case.json", "skills/x/tasks.json"])

    def test_case_data_may_hold_the_prompt_but_never_the_world(self):
        prompt = "Write a short poem about the quiet harbour at dawn for the notes app."
        expected = OWN_TEXT.replace("syllables", "words")
        other = [(self.tmp / "tasks.json", f'{{"prompt": "{prompt}", "expected": "{expected}"}}')]
        self.assertEqual(self.problems({"README.md": "x\n"}, {"prompt": prompt}, case_data=other), [])
        planted = self.problems({"data/q.json": other[0][1]}, case_data=other)
        self.assertTrue(any("data/q.json: holds eval text" in p for p in planted), planted)
        message = "Start the notes app with tags, search and a list of recent notes"
        own = self.tmp / "cases" / f"c{len(list((self.tmp / 'cases').iterdir())) + 1}" / "case.json"
        commits = {"commits": [{"message": message, "paths": ["README.md"]}]}
        self.assertEqual(self.problems({"README.md": "x\n"}, commits, case_data=[(own, message)]), [])
        sibling = [(self.tmp / "b.json", f'{{"commits": [{{"message": "{message}"}}]}}')]
        self.assertEqual(self.problems({"README.md": "x\n"}, commits, case_data=sibling), [])

    def test_the_projects_run_folder_is_not_a_tell(self):
        story = ".harness/runs/2026-10-30-notes/stories/S01.md"
        self.assertEqual(self.problems({story: "Tags sort by name.\n"}, {"prompt": f"Write claims for {story}."}), [])
        old = [(self.tmp / "tasks.json", f'{{"prompt": "Write claims for {story} now."}}')]
        self.assertEqual(self.problems({story: "Tags sort by name.\n"}, case_data=old), [])

    def test_lint_skill_reports_an_unbuildable_case(self):
        self.skill()
        case = self.case({"README.md": "x\n"}, name="linked")
        (case.world / "out").symlink_to("../../..")
        problems = lint.lint_skill("haiku-writer", Adapter, self.tmp / "cases", self.tmp / "skills", self.tmp)
        self.assertTrue(any("unsound" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
