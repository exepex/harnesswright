"""Goldens: hand-made runs of a case with settled answers, graded as runs are, and the golden gate."""

import json
import unittest

from helpers import TempCase, expect
from test_host import fake_adapter

import checks
import goldens
import grading
import view

CHANGED = {"name": "file_state", "args": {"path": "notes.txt", "state": "changed"}}
EXPECT = [expect("The notes are written", check=CHANGED), expect("The answer is short")]
SETTLED = {"q1": {"expectation": "The notes are written", "answer": "yes", "by": "fable"},
           "q2": {"expectation": "The answer is short", "answer": "no", "by": "fable"}}
LOG = [{"kind": "write", "source": "observed", "path": "notes.txt", "sha256": None},
       {"kind": "command", "source": "observed", "command": "cat README.md", "output": "", "exit_code": 0},
       {"kind": "message", "source": "observed", "text": "Wrote the notes."}]
GOLDEN = {"changes": {"notes.txt": "Buy milk.\n", "README.md": None}, "log": LOG, "settled": SETTLED}


class Goldens(TempCase):
    def setUp(self):
        super().setUp()
        self.skill()
        self.subject = self.case({"README.md": "A notes app.\n", "src/app.py": "print('hi')\n"},
                                 {"expectations": EXPECT})
        self.folder = self.tmp / "goldens"
        self.folder.mkdir()

    def write(self, name, data):
        (self.folder / name).write_text(json.dumps(data) if isinstance(data, dict) else data)

    def test_a_golden_is_a_run_on_the_case_s_world_and_is_graded_as_one(self):
        self.write("writes-notes.json", GOLDEN)
        [golden] = goldens.load(self.subject, self.folder)
        self.assertEqual((golden.name, golden.settled), ("writes-notes", {"q1": "yes", "q2": "no"}))
        record, blobs = goldens.bundle(golden, self.subject, fake_adapter(), self.tmp / "arm",
                                       self.tmp / "skills")
        self.assertEqual(sorted(record["diff"]), ["README.md", "notes.txt"])
        self.assertEqual((record["diff"]["notes.txt"]["before"], record["diff"]["README.md"]["after"]), (None, None))
        self.assertEqual(blobs[record["files_after"]["notes.txt"].split(" ")[1]], b"Buy milk.\n")
        self.assertIn("src/app.py", record["files_after"])  # the rest of the case's world is there as built
        verdict = checks.decide(CHANGED["name"], checks.Bundle(record, blobs.__getitem__), CHANGED["args"])
        self.assertEqual(verdict["outcome"], "pass")
        page = grading.page(*view.view(record, blobs.__getitem__))
        self.assertIn("Wrote the notes.", page)
        self.assertIn("Buy milk.", page)
        self.assertIn("  - command: cat README.md", page)
        self.assertNotIn("output", page)  # a command is shown as run, as in every run's view

    def test_a_case_without_goldens_has_none(self):
        self.assertEqual(goldens.load(self.subject, self.tmp / "none"), [])

    def test_a_golden_that_is_not_one_of_the_case_is_refused_with_why(self):
        moved = {**SETTLED, "q2": {**SETTLED["q2"], "expectation": "The answer is long"}}
        for name, data, why in (
                ("extra.json", {**GOLDEN, "final_message": "x"}, "nothing else"),
                ("path.json", {**GOLDEN, "changes": {"../out.txt": "x"}}, "inside the world"),
                ("log.json", {**GOLDEN, "log": [{"kind": "message", "text": "x"}]}, "action log"),
                ("missing.json", {**GOLDEN, "settled": {"q1": SETTLED["q1"]}}, "one answer for each expectation"),
                ("moved.json", {**GOLDEN, "settled": moved}, "not the case's own"),
                ("maybe.json", {**GOLDEN, "settled": {**SETTLED, "q1": {**SETTLED["q1"], "answer": "maybe"}}},
                 "yes or no"),
                ("notes.txt", "{}", "a golden is a file"),
                ("broken.json", "{", "not UTF-8 JSON")):
            with self.subTest(name=name):
                for path in self.folder.iterdir():
                    path.unlink()
                self.write(name, data)
                with self.assertRaisesRegex(goldens.GoldenError, why):
                    goldens.load(self.subject, self.folder)


class Gate(TempCase):
    def setUp(self):
        super().setUp()
        self.subject = self.case({"README.md": "A notes app.\n"}, {"expectations": EXPECT})
        flip = {id_: {**given, "answer": "no" if given["answer"] == "yes" else "yes"} for id_, given in SETTLED.items()}
        self.goldens = [goldens.Golden("a", GOLDEN), goldens.Golden("b", {**GOLDEN, "settled": flip})]

    def test_a_question_is_trusted_when_every_golden_asked_it_got_its_settled_answer_both_ways(self):
        graded = {"a": (["q1", "q2"], {"q1": "yes", "q2": "no"}), "b": (["q1", "q2"], {"q1": "no", "q2": "yes"})}
        self.assertEqual(goldens.gate(self.subject, self.goldens, graded), {"q1": None, "q2": None})

    def test_one_miss_or_one_unanswered_golden_is_enough(self):
        graded = {"a": (["q1", "q2"], {"q1": "yes", "q2": "yes"}), "b": (["q1", "q2"], {"q2": "yes"})}
        found = goldens.gate(self.subject, self.goldens, graded)
        self.assertEqual(found["q2"], "a golden was missed: a got yes, not no")
        self.assertEqual(found["q1"], "a golden was missed: b got no answer, not no")

    def test_a_question_no_golden_was_asked_both_ways_is_not_trusted(self):
        graded = {"a": (["q2"], {"q2": "no"}), "b": ([], {})}  # a check decided q1 on both, and q2 on b
        found = goldens.gate(self.subject, self.goldens, graded)
        self.assertEqual(set(found), {"q1", "q2"})
        self.assertIn("settled yes and one with a settled no", found["q1"])
        self.assertIn("settled yes and one with a settled no", found["q2"])
        self.assertEqual(goldens.gate(self.subject, [], {}), {"q1": found["q1"], "q2": found["q1"]})


if __name__ == "__main__":
    unittest.main()
