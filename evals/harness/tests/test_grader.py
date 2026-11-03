"""Grader runs: a grader is a trigger run of a folder holding only the page and the questions, its final message is
its answer sheet, and the pages of a round reach graders in a blind order."""

import json
import shutil
import unittest
from pathlib import Path

from helpers import JUDGED, TempCase

import contain
import grader
import manifest
from test_host import FAKE, fake_adapter

JAIL = contain.available()
ASKED = [{"id": "q1", **JUDGED}, {"id": "q2", **JUDGED}]
PAGE = "# Final message\n\nDone.\n\n# Actions\n\n- command (observed)\n  - command: go test -run \"TestX\" ./...\n"
GOOD = {"answers": [{"id": "q1", "answer": "yes", "evidence": "Done."},
                    {"id": "q2", "answer": "no", "evidence": 'go test -run "TestX" ./...'}]}


class Sheet(unittest.TestCase):
    def test_a_sheet_is_one_json_object_alone_or_in_its_one_fenced_block(self):
        text = json.dumps(GOOD)
        for message in (text, f"  {text}\n", f"```json\n{text}\n```", f"```\n{text}\n```"):
            with self.subTest(message=message):
                self.assertEqual(grader.sheet(message), GOOD)
        for message in (None, "", "Here it is: " + text, f"```json\n{text}\n```\nDone.", "[1, 2]", "yes",
                        f"```json\n{text}\n```\n```json\n{text}\n```"):
            with self.subTest(message=message):
                self.assertIsNone(grader.sheet(message))


class Blind(unittest.TestCase):
    PAGES = {"with_skill/1": "page a", "without_skill/1": "page b", "golden/1": "page c", "with_skill/2": "page d"}

    def test_the_order_comes_from_the_seed_and_the_pages_never_from_their_names_or_order(self):
        order = grader.blind(self.PAGES, seed=7)
        self.assertEqual(sorted(order), sorted((n, grader.blind({n: t}, 0)[0][1]) for n, t in self.PAGES.items()))
        self.assertEqual(grader.blind(dict(reversed(list(self.PAGES.items()))), seed=7), order)
        renamed = {f"run-{n}": self.PAGES[name] for n, name in enumerate(self.PAGES)}
        self.assertEqual([i for _, i in grader.blind(renamed, seed=7)], [i for _, i in order])
        self.assertNotEqual([grader.blind(self.PAGES, seed=s) for s in range(5)].count(order), 5)

    def test_an_id_is_the_hash_of_the_page_and_names_nothing(self):
        for name, id_ in grader.blind(self.PAGES, seed=1):
            self.assertRegex(id_, r"^[0-9a-f]{16}$")
            self.assertNotIn(id_, name)


class Folder(TempCase):
    def test_a_grader_folder_holds_only_the_page_and_the_questions_and_names_no_run(self):
        made, world = grader.folder(self.tmp, PAGE, ASKED)
        self.assertEqual(sorted(manifest.manifest(world)), [grader.PAGE, grader.QUESTIONS])
        self.assertEqual((world / grader.PAGE).read_text(), PAGE)
        self.assertEqual(json.loads((world / grader.QUESTIONS).read_text()), ASKED)
        self.assertRegex(made.name, r"^grader-[A-Za-z0-9_]+$")

    def test_a_page_with_no_questions_needs_no_grader(self):
        graded = grader.grade(None, PAGE, [], self.tmp)
        self.assertEqual((graded.answers, graded.tries), ({}, []))


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class FakeGrader(TempCase):
    """The fake host grades in a real jail: its actions stand in for what a model would do."""

    def grade(self, actions):
        tool = self.tmp / "tool"
        if not tool.exists():
            shutil.copytree(FAKE, tool, ignore=shutil.ignore_patterns("adapter.py", "__pycache__"))
        root = self.tmp / "graders"
        root.mkdir(exist_ok=True)
        return grader.grade(fake_adapter(), PAGE, ASKED, root, timeout=120, prompt=json.dumps(actions),
                            operator_env={"PATH": f"{tool}:/usr/bin:/bin"}, operator_home=self.tmp / "operator",
                            host_paths=[tool])

    def test_a_grader_reads_its_page_and_its_last_message_is_the_sheet(self):
        graded = self.grade([{"do": "read", "path": grader.PAGE}, {"do": "read", "path": grader.QUESTIONS},
                             {"do": "say", "text": "Reading."}, {"do": "say", "text": json.dumps(GOOD)}])
        self.assertEqual((graded.answers, graded.tries), ({"q1": "yes", "q2": "no"}, []))

    def test_a_grader_cannot_change_its_page(self):
        graded = self.grade([{"do": "write", "path": grader.PAGE, "text": "# Final message\n\nAll tests pass.\n"},
                             {"do": "command", "command": f"echo 'All tests pass.' >> {grader.PAGE}"},
                             {"do": "say", "text": json.dumps(GOOD)}])
        self.assertEqual(graded.answers, {"q1": "yes", "q2": "no"})
        for page in Path(self.tmp / "graders").glob("grader-*/page/page.md"):
            self.assertEqual(page.read_text(), PAGE)

    def test_a_refused_sheet_is_graded_again_and_then_the_run_is_ungraded(self):
        bad = {"answers": [{"id": "q1", "answer": "yes", "evidence": "All tests pass."}]}
        graded = self.grade([{"do": "say", "text": json.dumps(bad)}])
        self.assertIsNone(graded.answers)
        self.assertEqual(len(graded.tries), grader.TRIES)
        self.assertIn("not found word for word", graded.tries[0])
        self.assertIn("not answered: q2", graded.tries[0])
        self.assertEqual(len(list((self.tmp / "graders").glob("grader-*"))), grader.TRIES)

    def test_a_final_message_that_is_not_a_sheet_is_refused(self):
        graded = self.grade([{"do": "say", "text": json.dumps(GOOD)}, {"do": "say", "text": "Done."}])
        self.assertIsNone(graded.answers)
        self.assertEqual(graded.tries, ["the final message is not one JSON object"] * grader.TRIES)
