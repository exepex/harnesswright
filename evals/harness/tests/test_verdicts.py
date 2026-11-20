"""The task and trigger outcomes: whether a task run passed its contract expectations, and whether a trigger run
loaded the skill exactly when it should."""

import unittest

from test_labels import EXPECTATIONS, case, verdict

import triggers
import verdicts


class Outcomes(unittest.TestCase):
    def test_a_task_run_counts_its_contract_expectations_a_check_first_then_a_trusted_answer(self):
        self.assertEqual(verdicts.task_outcome(case(), [verdict("fail"), None, verdict("pass")], {"q2": "yes"}),
                         (True, ""))  # the format check that failed does not count
        self.assertEqual(verdicts.task_outcome(case(), [verdict("pass"), None, verdict("pass")], {"q2": "no"}),
                         (False, "expectation 2 failed"))
        self.assertEqual(verdicts.task_outcome(case(), [verdict("pass"), None, verdict("undecidable")],
                                               {"q2": "yes", "q3": "no"}), (False, "expectation 3 failed"))
        self.assertEqual(verdicts.task_outcome(case(), [verdict("pass"), None, verdict("pass")], {}),
                         (None, "expectation 2 has no trusted answer"))  # untrusted or unanswered
        self.assertEqual(verdicts.task_outcome(case(), [verdict("pass"), None, verdict("fail")], {})[0], False)
        self.assertEqual(verdicts.task_outcome(case(expectations=EXPECTATIONS[:1]), [verdict("pass")], {}),
                         (None, "the case has no contract expectation"))

    def test_a_trigger_run_passes_when_the_skill_loaded_exactly_when_it_should_an_inferred_load_named(self):
        def load(name, source="observed"):
            return [{"kind": "skill", "source": source, "name": name}]

        should, should_not = case("trigger", should_trigger=True), case("trigger", should_trigger=False)
        self.assertEqual(triggers.trigger_outcome(should, load("haiku-writer")), (True, False))
        self.assertEqual(triggers.trigger_outcome(should, load("other-skill")), (False, False))
        self.assertEqual(triggers.trigger_outcome(should_not, load("other-skill")), (True, False))
        self.assertEqual(triggers.trigger_outcome(should_not, load("haiku-writer")), (False, False))
        self.assertEqual(triggers.trigger_outcome(should, load("haiku-writer", "inferred")), (True, True))
        self.assertEqual(triggers.trigger_outcome(should_not, load("haiku-writer", "inferred")), (False, True))
        both = load("haiku-writer", "inferred") + load("haiku-writer")
        self.assertEqual(triggers.trigger_outcome(should, both), (True, False))

