"""Goldens: hand-made runs of a case with settled answers, made into bundles as runs are, and the golden gate."""

import json
import os
import types
import unittest

from helpers import JUDGED, TempCase, expect
from test_host import fake_adapter

import cases
import checks
import evidence
import goldens
import grading
import view

CHANGED = {"name": "file_state", "args": {"path": "notes.txt", "state": "changed"}}
EXPECT = [expect("The notes are written", check=CHANGED), expect("The answer is short")]
LOG = [{"kind": "write", "source": "observed", "path": "notes.txt", "sha256": None},
       {"kind": "command", "source": "observed", "command": "cat README.md", "output": "A notes app.\n",
        "exit_code": 0},
       {"kind": "message", "source": "observed", "text": "Wrote the notes."}]
DRIFT = {"own files": {"task": [], "trigger": []}}


def settled(answers=("yes", "no", "yes"), expectations=(*EXPECT, cases.done())):
    """Settled answers for each expectation, the done question every task case ends with last."""
    return {f"q{n}": {"expectation": item["text"], "sha256": goldens.fingerprint(item), "answer": answer,
                      "by": "judge-a"} for n, (item, answer) in enumerate(zip(expectations, answers), start=1)}


GOLDEN = {"changes": {"notes.txt": "Buy milk.\n", "README.md": None}, "log": LOG, "settled": settled()}


class Goldens(TempCase):
    def setUp(self):
        super().setUp()
        self.skill()
        self.subject = self.case({"README.md": "A notes app.\n", "run.sh": "echo hi\n"}, {"expectations": EXPECT,
                                 "skill_path": ".harness/active"})
        os.chmod(self.subject.world / "run.sh", 0o755)
        self.folder = self.tmp / "goldens"
        self.folder.mkdir()

    def write(self, name, data):
        (self.folder / name).write_text(json.dumps(data) if isinstance(data, dict) else data)

    def built(self, data, out="out"):
        self.write("g.json", data)
        [golden] = goldens.load(self.subject, self.folder)
        return goldens.bundle(golden, self.subject, fake_adapter(), self.tmp / out, DRIFT, "fakehost 1.0", "fast",
                              self.tmp / "skills")

    def test_a_golden_becomes_a_bundle_as_a_run_does_and_is_graded_as_one(self):
        record, blobs = self.built(GOLDEN)
        self.assertEqual(record["overlay"], evidence.overlay(self.subject, fake_adapter(), self.tmp / "skills"))
        self.assertEqual((record["arm"], sorted(record["diff"])), ("golden", ["README.md", "notes.txt"]))
        self.assertEqual(record["log"][2], {"kind": "read", "source": "inferred", "path": "README.md"})  # as a host's
        out = evidence.store(record, blobs, self.tmp / "stored")  # a bundle like any other, stored and read back
        loaded, blob = evidence.load(out)
        self.assertEqual(checks.decide(CHANGED["name"], checks.Bundle(loaded, blob), CHANGED["args"])["outcome"],
                         "pass")
        page = grading.page("Write the notes.", *view.view(loaded, blob))
        for shown in ("Wrote the notes.", "Buy milk.", "  - command: cat README.md"):
            self.assertIn(shown, page)
        self.assertNotIn("A notes app.", page)  # a command's output never reaches a grader, as in every run

    def test_a_golden_of_a_skill_with_no_folder_yet_is_a_run_without_the_skill(self):
        new = self.case({"README.md": "A notes app.\n"}, {"expectations": EXPECT}, skill="limerick-writer")
        self.write("g.json", GOLDEN)
        [golden] = goldens.load(new, self.folder)
        record, _ = goldens.bundle(golden, new, fake_adapter(), self.tmp / "out", DRIFT, "fakehost 1.0", "fast",
                                   self.tmp / "skills")  # the grade gate builds every golden so
        self.assertEqual(record["overlay"], {"skill": "limerick-writer", "paths": [], "release": [], "index": None,
                                             "row": None, "index_without": None, "edited": {}})
        self.assertEqual(sorted(record["diff"]), ["README.md", "notes.txt"])

    def test_a_golden_s_text_is_seen_through_the_same_view_as_a_run_s(self):
        log = [*LOG[:2], {"kind": "message", "source": "observed", "text": "Read .harness/active/SKILL.md.\nDone."}]
        record, blobs = self.built({**GOLDEN, "log": log})
        page = grading.page("Write the notes.", *view.view(record, blobs.__getitem__))
        self.assertNotIn(".harness/active", page)  # the skill's path is the overlay's, whatever its name
        self.assertIn("Done.", page)

    def test_a_file_written_again_keeps_its_mode_and_a_change_a_run_could_not_make_is_refused(self):
        record, blobs = self.built({**GOLDEN, "changes": {"run.sh": "echo hi\n", "notes.txt": "Café ☕\n"}})
        self.assertEqual(blobs[record["files_after"]["notes.txt"].split(" ")[1]], "Café ☕\n".encode())
        self.assertEqual(sorted(record["diff"]), ["notes.txt"])  # the same text written again is no change
        for number, changes in enumerate(({"src": None}, {"run.sh/x": "y"}, {"gone.txt": None}), start=1):
            with self.subTest(changes=changes), self.assertRaisesRegex(goldens.GoldenError, "not a file of the world"):
                self.built({**GOLDEN, "changes": changes}, f"out{number}")
        loads = [{"kind": "skill", "source": "observed", "name": "haiku-writer"}]  # the skill under test is not there
        with self.assertRaisesRegex(goldens.GoldenError, "haiku-writer was loaded"):
            self.built({**GOLDEN, "log": loads}, "out-skill")

    def test_a_trigger_golden_changes_nothing_as_a_trigger_run_cannot(self):
        trigger = types.SimpleNamespace(kind="trigger", expectations=EXPECT, skill="haiku-writer", id="t")
        no_done = {**GOLDEN, "settled": settled(expectations=EXPECT)}  # a trigger case has no done question
        self.write("g.json", no_done)
        with self.assertRaisesRegex(goldens.GoldenError, "read-only"):
            goldens.load(trigger, self.folder)
        self.write("g.json", {**no_done, "changes": {}})
        self.assertEqual([g.name for g in goldens.load(trigger, self.folder)], ["g"])

    def test_a_case_without_goldens_has_none(self):
        self.assertEqual(goldens.load(self.subject, self.tmp / "none"), [])

    def test_a_golden_that_is_not_one_of_the_case_is_refused_with_why(self):
        changed = [EXPECT[0], {**EXPECT[1], "judged": {**JUDGED, "pass": "It holds, mostly."}}]
        for name, data, why in (
                ("extra.json", {**GOLDEN, "final_message": "x"}, "nothing else"),
                ("path.json", {**GOLDEN, "changes": {"../out.txt": "x"}}, "inside the world"),
                ("log.json", {**GOLDEN, "log": [{"kind": "message", "text": "x"}]}, "action log"),
                ("arm-path.json", {**GOLDEN, "changes": {"with_skill.txt": "x"}}, "names the arm 'with_skill'"),
                ("arm-text.json", {**GOLDEN, "changes": {"a.txt": "configuration: without_skill"}}, "names the arm"),
                ("arm-log.json", {**GOLDEN, "log": [*GOLDEN["log"], {"kind": "message", "text": "previous_version"}]},
                 "names the arm 'previous_version'"),
                ("missing.json", {**GOLDEN, "settled": {"q1": GOLDEN["settled"]["q1"]}}, "one answer for each"),
                ("changed.json", {**GOLDEN, "settled": settled(expectations=(*changed, cases.done()))}, "as it is now"),
                ("maybe.json", {**GOLDEN, "settled": settled(("yes", "maybe", "yes"))}, "yes or no"),
                ("by.json", {**GOLDEN, "settled": {**GOLDEN["settled"], "q1": {**GOLDEN["settled"]["q1"], "by": ""}}},
                 "by names the judge"),
                ("surrogate.json", json.dumps({**GOLDEN, "changes": {"a.txt": "\ud800"}}), "not UTF-8 JSON"),
                ("notes.txt", "{}", "a golden is a file"),
                ("broken.json", "{", "not UTF-8 JSON")):
            with self.subTest(name=name):
                for path in self.folder.iterdir():
                    path.unlink()
                self.write(name, data)
                with self.assertRaisesRegex(goldens.GoldenError, why):
                    goldens.load(self.subject, self.folder)


class Repository(TempCase):
    def test_every_golden_of_the_repository_builds_as_a_run_and_settles_each_question_both_ways(self):
        skills = sorted(goldens.ROOT.iterdir()) if goldens.ROOT.is_dir() else []
        for folder in (case for skill in skills for case in sorted(skill.iterdir())):
            with self.subTest(case=f"{folder.parent.name}/{folder.name}"):
                [case] = [c for c in cases.load_cases(folder.parent.name) if c.id == folder.name]
                found = goldens.load(case)
                self.assertTrue(found)
                self.assertEqual(goldens.uncovered(case, found), [])
                for golden in found:
                    goldens.bundle(golden, case, fake_adapter(), self.tmp / folder.name / golden.name, DRIFT,
                                   "fakehost 1.0", "fast")


class Gate(TempCase):
    def setUp(self):
        super().setUp()
        self.subject = self.case({"README.md": "A notes app.\n"}, {"expectations": EXPECT})
        self.goldens = [goldens.Golden("a", GOLDEN), goldens.Golden("b", {**GOLDEN, "settled": settled(("no", "yes", "no"))})]

    def test_a_question_is_trusted_when_every_golden_asked_it_got_its_settled_answer_both_ways(self):
        graded = {"a": (["q1", "q2", "q3"], {"q1": "yes", "q2": "no", "q3": "yes"}, []),
                  "b": (["q1", "q2", "q3"], {"q1": "no", "q2": "yes", "q3": "no"}, [])}
        self.assertEqual(goldens.gate(self.subject, self.goldens, graded), {"q1": None, "q2": None, "q3": None})

    def test_one_miss_or_one_unanswered_golden_is_enough(self):
        graded = {"a": (["q1", "q2"], {"q1": "yes", "q2": "yes"}, []), "b": (["q1", "q2"], {"q2": "yes"}, [])}
        found = goldens.gate(self.subject, self.goldens, graded)
        self.assertEqual(found["q2"], "a golden was missed: a got yes, not no")
        self.assertEqual(found["q1"], "a golden was missed: b got no answer, not no")

    def test_a_question_no_golden_was_asked_both_ways_is_not_trusted(self):
        graded = {"a": (["q2"], {"q2": "no"}, []), "b": ([], {}, [])}  # a check decided q1 on both, and q2 on b
        found = goldens.gate(self.subject, self.goldens, graded)
        self.assertIn("settled yes and one with a settled no", found["q1"])
        self.assertIn("settled yes and one with a settled no", found["q2"])
        self.assertEqual(goldens.gate(self.subject, [], {}), dict.fromkeys(("q1", "q2", "q3"), found["q1"]))
        self.assertEqual((goldens.uncovered(self.subject, self.goldens), goldens.uncovered(self.subject, [])),
                         ([], ["q1", "q2", "q3"]))

    def test_a_golden_that_was_not_graded_cannot_drop_out(self):
        for graded in ({"a": (["q1", "q2"], {"q1": "yes", "q2": "no"}, [])},
                       {"a": ([], {}, []), "b": ([], {}, []), "c": ([], {}, [])}):
            with self.subTest(graded=sorted(graded)), self.assertRaisesRegex(goldens.GoldenError, "every golden"):
                goldens.gate(self.subject, self.goldens, graded)


if __name__ == "__main__":
    unittest.main()
