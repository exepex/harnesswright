"""The stop pair (stoppair.py): every task case of a skill with check scripts is asked it, and writes none of it."""

import json
import unittest
from unittest import mock

from helpers import TempCase

import cases
import checks
import stoppair
import verdicts
from cases import CaseError

DECLARED = {"haiku-writer": {"count.py": {"0": "", "127": "not found"},
                             "lint.py": {"0": "", "2": "lint stopped:", "127": "not found"}}}


class StopPair(TempCase):
    def declared(self, data=DECLARED):
        return mock.patch.object(stoppair, "skill_checks", lambda path=None: data)

    def test_a_task_case_of_a_skill_with_checks_gets_the_pair_before_the_done_question(self):
        with self.declared():
            task = self.case({"a.txt": "x\n"})
            trigger = self.case({}, {"kind": "trigger", "should_trigger": True, "split": "test",
                                     "index": {"file": "a.txt", "after": "x", "row": "{name}"}})
        sources = [e["source"] for e in task.expectations]
        self.assertEqual(sources, ["stop", "stop", "done"])
        checked, named = task.expectations[:2]
        self.assertEqual(checked["check"], {"name": "blocked_after_failed_check", "args": {"skill": "haiku-writer"}})
        self.assertNotIn("check", named)
        for expectation in (checked, named):  # each question names every script and the codes that are no failure
            question = expectation["judged"]["question"]
            self.assertIn("the last run of its count.py ended with any exit code but 0 or 127 with `not found` in "
                          "its output, or the last run of its lint.py ended with any exit code but 0, 2 with `lint "
                          "stopped:` in its output or 127 with `not found` in its output", question)
            self.assertNotIn("{", question)
        self.assertFalse([e for e in trigger.expectations or [] if e["source"] == "stop"])

    def test_a_skill_with_no_declared_check_gets_no_pair(self):
        with self.declared({}):
            self.assertEqual([e["source"] for e in self.case({}).expectations], ["done"])

    def test_the_pair_and_the_declaration_are_part_of_the_case_hash(self):
        with self.declared():
            first = self.case({}, name="same").sha256
        text = json.loads(stoppair.STOP.read_text())
        text[1]["judged"]["fail"] += " Changed."
        (self.tmp / "stop.json").write_text(json.dumps(text))
        with self.declared(), mock.patch.object(stoppair, "STOP", self.tmp / "stop.json"):
            changed = cases.Case(self.tmp / "cases" / "same", "haiku-writer")
        self.assertNotEqual(first, changed.sha256)
        self.assertTrue(changed.expectations[1]["judged"]["fail"].endswith(" Changed."))

    def test_a_case_that_writes_the_stop_check_itself_is_refused(self):
        expectation = {"text": "Stops", "source": "format", "check": {"name": "blocked_after_failed_check",
                                                                     "args": {"skill": "claims-writer"}},
                       "judged": {"question": "Q?", "pass": "Yes.", "fail": "No.",
                                  "examples": {"pass": ["a"], "fail": ["b"]}}}
        with self.assertRaisesRegex(CaseError, "expectation 1: the stop check is the stop pair's"):
            self.case({}, {"expectations": [expectation]})

    def test_a_declaration_in_another_shape_is_refused(self):
        for wrong in ([], {"haiku-writer": {}}, {"haiku-writer": {"a.py": {"x": ""}}}, {"Haiku": {"a.py": {"0": ""}}}):
            (self.tmp / "checks.json").write_text(json.dumps(wrong))
            with self.subTest(wrong=wrong), self.assertRaisesRegex(CaseError, "must map each skill"):
                stoppair.skill_checks(self.tmp / "checks.json")

    def test_the_pair_counts_in_the_task_outcome(self):
        with self.declared():
            case = self.case({})
        fail = {"check": "blocked_after_failed_check", "outcome": "fail", "reason": "r", "inferred": False}
        passed = dict(fail, outcome="pass")
        self.assertEqual(verdicts.task_outcome(case, [fail, None, None], {"q2": "yes"})[0], False)
        self.assertEqual(verdicts.task_outcome(case, [passed, None, None], {"q2": "no"})[0], False)
        self.assertEqual(verdicts.task_outcome(case, [passed, None, None], {"q2": "yes"}), (True, ""))
        self.assertEqual(verdicts.task_outcome(case, [passed, None, None], {})[0], None)  # 3b has no answer yet

    def test_where_scripts_are_forbidden_the_check_passes_and_both_questions_read_as_passed(self):
        bundle = checks.Bundle.key({"log": [{"kind": "command", "source": "observed", "command": "cat a.txt",
                                             "exit_code": 0, "output": "x"}],
                                    "final_message": "The profile forbids scripts, so I read the rules by hand."})
        found = checks.decide("blocked_after_failed_check", bundle, {"skill": "claims-writer"})
        self.assertEqual(found["outcome"], "pass")
        checked, named = stoppair.stop("claims-writer")
        self.assertIn("as when the project forbids scripts", checked["judged"]["pass"])
        self.assertIn("as when none of its scripts ran because the project forbids scripts", named["judged"]["pass"])

    def test_every_skill_with_a_kind_declares_its_checks(self):
        self.assertEqual(sorted(stoppair.skill_checks()), sorted(cases.kinds()))


if __name__ == "__main__":
    unittest.main()
