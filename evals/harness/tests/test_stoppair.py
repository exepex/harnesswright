"""The stop pair (stoppair.py): two script checks that every task run of a skill with check scripts is decided by,
which no case writes, reported per arm and never counted or graded."""

import json
import unittest
from unittest import mock

from helpers import TempCase

import cases
import checks
import stoppair
from cases import CaseError

DECLARED = {"haiku-writer": {"count.py": {"0": "", "127": "not found"}}}


class StopPair(TempCase):
    def declared(self, data=DECLARED):
        return mock.patch.object(stoppair, "skill_checks", lambda path=None: data)

    def test_a_task_case_of_a_skill_with_checks_is_reported_the_pair_and_asked_none_of_it(self):
        with self.declared():
            task = self.case({"a.txt": "x\n"})
            trigger = self.case({}, {"kind": "trigger", "should_trigger": True, "split": "test",
                                     "index": {"file": "a.txt", "after": "x", "row": "{name}"}})
        self.assertEqual([e["source"] for e in task.expectations], ["done"])  # nothing to grade, nothing counted
        self.assertEqual([e["check"] for e in task.reported],
                         [{"name": name, "args": {"skill": "haiku-writer"}} for name in stoppair.CHECKS])
        self.assertFalse([e for e in task.reported if "judged" in e])
        self.assertEqual(trigger.reported, [])

    def test_a_skill_with_no_declared_check_gets_no_pair(self):
        with self.declared({}):
            self.assertEqual(self.case({}).reported, [])

    def test_the_pair_and_the_declaration_are_part_of_the_case_hash(self):
        with self.declared():
            first = self.case({}, name="same").sha256
        text = json.loads(stoppair.STOP.read_text())
        text[1]["text"] += " Changed."
        (self.tmp / "stop.json").write_text(json.dumps(text))
        with self.declared(), mock.patch.object(stoppair, "STOP", self.tmp / "stop.json"):
            changed = cases.Case(self.tmp / "cases" / "same", "haiku-writer")
        self.assertNotEqual(first, changed.sha256)

    def test_a_case_that_writes_a_stop_check_itself_is_refused(self):
        for name in stoppair.CHECKS:
            expectation = {"text": "Stops", "source": "format", "check": {"name": name,
                                                                         "args": {"skill": "claims-writer"}},
                           "judged": {"question": "Q?", "pass": "Yes.", "fail": "No.",
                                      "examples": {"pass": ["a"], "fail": ["b"]}}}
            with self.subTest(name), self.assertRaisesRegex(CaseError, f"expectation 1: {name} is the stop pair's"):
                self.case({}, {"expectations": [expectation]})

    def test_a_declaration_or_a_pair_in_another_shape_is_refused(self):
        for wrong in ([], {"haiku-writer": {}}, {"haiku-writer": {"a.py": {"x": ""}}}, {"Haiku": {"a.py": {"0": ""}}}):
            (self.tmp / "checks.json").write_text(json.dumps(wrong))
            with self.subTest(wrong=wrong), self.assertRaisesRegex(CaseError, "must map each skill"):
                stoppair.skill_checks(self.tmp / "checks.json")
        pair = json.loads(stoppair.STOP.read_text())
        judged = {"question": "Q?", "pass": "Yes.", "fail": "No.", "examples": {"pass": ["a"], "fail": ["b"]}}
        for wrong in (pair[:1], pair[::-1], [dict(pair[0], judged=judged), pair[1]]):  # no question, ever
            (self.tmp / "stop.json").write_text(json.dumps(wrong))
            with self.subTest(wrong=wrong), self.assertRaisesRegex(CaseError, "and no judged question"):
                stoppair.stop("claims-writer", self.tmp / "stop.json")

    def test_where_scripts_are_forbidden_both_checks_pass(self):
        bundle = checks.Bundle.key({"log": [{"kind": "command", "source": "observed", "command": "cat a.txt",
                                             "exit_code": 0, "output": "x"}],
                                    "final_message": "The profile forbids scripts, so I read the rules by hand."})
        for name in stoppair.CHECKS:
            with self.subTest(name):
                self.assertEqual(checks.decide(name, bundle, {"skill": "claims-writer"})["outcome"], "pass")

    def test_every_skill_with_a_kind_declares_its_checks(self):
        self.assertEqual(sorted(stoppair.skill_checks()), sorted(cases.kinds()))


if __name__ == "__main__":
    unittest.main()
