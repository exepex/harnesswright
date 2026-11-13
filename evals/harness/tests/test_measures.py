"""The label file's other measures: each read from the store, and none estimated."""

import json
import unittest
from unittest import mock

from helpers import TempCase
from test_labels import EXPECTATIONS, case
from test_prices import PRICES, counts

import measures


def verdict(outcome, inferred=False):
    return {"check": "file_state", "outcome": outcome, "reason": "planted", "inferred": inferred}


class Measures(TempCase):
    """A store with runs of one task case and one trigger case, laid out as a round lays them out."""

    def setUp(self):
        super().setUp()
        self.made, self.records, self.graded = [], {}, []

    def run_(self, key, arm, status="made", voids=0, record=None, verdicts=None, answers=None, agreed=(0, 0),
             case_id="t"):
        folder = self.tmp / "runs" / key
        folder.mkdir(parents=True)
        if voids:
            (folder / "void.json").write_text(json.dumps({"reasons": ["the host failed"] * voids}))
        self.made.append({"host": "h", "skill": "haiku-writer", "case": case_id, "arm": arm, "key": key,
                          "status": status, "number": len(self.made) + 1})
        if status in ("kept", "made"):
            self.records[str(folder / "bundle")] = record or {"seconds": 10, "tokens": None}
        if verdicts is not None:
            (folder / "checks.json").write_text(json.dumps({"verdicts": verdicts}))
        if answers is not None:
            sheet = self.tmp / "grades" / "a1" / "runs" / f"{key}.json"
            sheet.parent.mkdir(parents=True, exist_ok=True)
            sheet.write_text(json.dumps({"answers": answers}))
            self.graded.append({"key": key, "agreed": agreed[0], "asked": agreed[1]})

    def measure(self, faults=None, goldens=None):
        gates = {"run": {"passed": True, "outcome": self.made},
                 "grade": {"passed": True, "outcome": {"goldens": goldens or {}, "runs": self.graded}}}
        if faults is not None:
            gates["faults"] = {"passed": True, "outcome": faults}
        cases = {("haiku-writer", "t"): case(expectations=EXPECTATIONS),
                 ("haiku-writer", "g"): case("trigger", should_trigger=True, split="test")}
        with mock.patch.object(measures.evidence, "load", lambda path: (self.records[str(path)], None)):
            return measures.measures(self.tmp, "a1", gates, cases, PRICES)[("h", "haiku-writer")]

    def test_voids_agreement_goldens_faults_inferred_evidence_and_format_are_each_counted(self):
        self.run_("k1", "with_skill", voids=1, verdicts=[verdict("pass"), None, verdict("pass")],
                  answers={"q2": "yes"}, agreed=(1, 1))  # a void, then a remake that was made
        self.run_("k2", "with_skill", verdicts=[verdict("fail"), None, verdict("undecidable", inferred=True)],
                  answers={"q2": "no", "q3": "yes"}, agreed=(1, 2))
        self.run_("k3", "without_skill", status="empty", voids=2)
        self.run_("k4", "without_skill", verdicts=[verdict("undecidable", inferred=True), None, verdict("fail")],
                  answers={"q1": "no", "q2": "no"}, agreed=(2, 2))
        self.run_("k5", "with_skill", case_id="g")  # a trigger run counts in the void rate and the cost only
        found = self.measure(faults={"h": [{"caught": True}, {"caught": True}], "other": [{"caught": True}]},
                             goldens={"haiku-writer/t": {"q2": None, "q3": "the no golden was answered yes"},
                                      "other-skill/t": {"q2": "planted"}})
        self.assertEqual(found["void_rate"], {"with_skill": 0.25, "without_skill": 0.6667})  # 1 of 4, 2 of 3
        self.assertEqual(found["grader_agreement"], 0.8)  # 4 of 5
        self.assertEqual(found["golden_accuracy"], 0.5)
        self.assertEqual(found["faults"], {"caught": 2, "planted": 2})
        self.assertEqual(found["inferred_evidence"], {"with_skill": 1, "without_skill": 1})
        # format: a check pass, a check fail; and a trusted "no" where an inferred check decided nothing
        self.assertEqual(found["format_conformance"], {"with_skill": 0.5, "without_skill": 0.0})

    def test_cost_sums_each_arm_and_gives_no_money_when_one_run_has_none(self):
        priced = {"seconds": 12.5, "tokens": {"model-a": counts(1_000_000, output=10_000)}}
        self.run_("k1", "with_skill", record=priced, verdicts=[None] * 3, answers={})
        self.run_("k2", "with_skill", record=priced, verdicts=[None] * 3, answers={})
        self.run_("k3", "without_skill", record={"seconds": None, "tokens": None}, verdicts=[None] * 3, answers={})
        self.run_("k4", "without_skill", record=priced, verdicts=[None] * 3, answers={})
        found = self.measure()
        self.assertEqual(found["cost"]["with_skill"], {
            "runs": 2, "seconds": 25.0, "untimed": 0, "unpriced": 0, "money": 4.2,
            "tokens": {"model-a": counts(2_000_000, output=20_000)}})
        self.assertEqual(found["cost"]["without_skill"]["money"], None)  # one run had no counts: never a guess
        self.assertEqual((found["cost"]["without_skill"]["unpriced"], found["cost"]["without_skill"]["untimed"]),
                         (1, 1))
        self.assertIsNone(found["faults"])  # no fault gate in this attempt
        self.assertEqual((found["grader_agreement"], found["golden_accuracy"]), (None, None))


if __name__ == "__main__":
    unittest.main()
