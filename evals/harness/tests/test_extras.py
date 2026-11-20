"""Extra runs (doc 12, Verdicts): only a too-close measure or floor adds runs, 3 to each split case it reads in each
arm it reads, at most as many as the plan's `extra_runs`, and never to the fault gate's planted runs."""

import json
from types import SimpleNamespace
from unittest import mock

from helpers import TempCase

import extras
import faults
import gates
import grades
import labels
import prices
import runs
from cases import PREVIOUS

CASES = {("s", i): SimpleNamespace(kind="task", skill="s", id=i) for i in ("c1", "c2", "c3")}


def verdict(state, **split):
    return {"verdict": state, "value": 0.9, "best": 1.0, "worst": 0.8, "split": split}


def label(**found):
    """A label file of skill `s` on host `h`, whose verdicts are `found`."""
    return {"skills": {"s": {"h": {"label": "x", "verdicts": found}}}}


class Wanted(TempCase):
    record = {"cases": {"s": {"c1": "", "c2": "", "c3": ""}}, "plan": {"runs": 3, "extra_runs": 6}}

    def test_a_clean_round_wants_no_run(self):
        found = label(**{"task pass rate": verdict("pass", with_skill=[]), "lift": verdict("fail", with_skill=["c1"],
                                                                                            without_skill=["c1"])})
        self.assertEqual(extras.wanted(found, self.record, CASES), set())  # a fail is decided too: no runs

    def test_a_too_close_measure_wants_each_split_case_it_reads_in_each_arm_it_reads(self):
        found = label(**{"lift": verdict("too close", with_skill=["c1"], without_skill=["c2"]),
                         "task pass rate": verdict("pass", with_skill=["c1"]),
                         "situation self-judge": verdict("too close", with_skill=["c3"])})
        self.assertEqual(extras.wanted(found, self.record, CASES), {
            ("h", "s", "c1", "with_skill"), ("h", "s", "c1", "without_skill"), ("h", "s", "c2", "with_skill"),
            ("h", "s", "c2", "without_skill"), ("h", "s", "c3", "with_skill")})  # a floor reads the with-skill arm
        internal = {**self.record, "kinds": {"s": "internal"}, "previous": {"s": {}}}
        found = label(**{"previous pass rate": verdict("too close", with_skill=["c1"], **{PREVIOUS: []})})
        self.assertEqual(extras.wanted(found, internal, CASES),
                         {("h", "s", "c1", "with_skill"), ("h", "s", "c1", PREVIOUS)})

    def test_an_extra_run_s_number_follows_the_planned_runs_up_to_the_plan_s_extra_runs(self):
        for extra, last in ((0, 3), (3, 6), (6, 9)):
            record = {"round": "r1", "cases": {"s": {"c1": "x"}}, "skills": {}, "hosts": {"h": {}},
                      "adapters": {"h": ""},
                      "plan": {"runs": 3, **({"extra_runs": extra} if extra else {})}}
            with self.subTest(extra=extra):
                runs.key(record, "s", "c1", "with_skill", "h", last, {}, code="0")
                with self.assertRaisesRegex(runs.RunError, f"run {last + 1}: not a run of round r1"):
                    runs.key(record, "s", "c1", "with_skill", "h", last + 1, {}, code="0")


class Gate(TempCase):
    def round(self, extra, *found):
        """A round after its grade gate whose labels are `found`, one per decision of the extra runs gate."""
        (self.tmp / "attempts").mkdir(exist_ok=True)
        planned = [{"host": "h", "skill": "s", "case": i, "arm": "with_skill", "number": 1, "key": i,
                    "status": "made"} for i in ("c1", "c2", "c3")]
        (self.tmp / "attempts" / "t1.json").write_text(json.dumps({"gates": [
            {"gate": "run", "passed": True, "outcome": planned}]}))
        r = SimpleNamespace(folder=self.tmp, attempt="t1", repo=self.tmp, cases=CASES, runs=[], asked={},
                            record={"cases": {"s": {"c1": "", "c2": "", "c3": ""}},
                                    "plan": {"runs": 3, **({"extra_runs": extra} if extra is not None else {})}})
        made, decisions = [], list(found)

        def run_one(r, host, skill, case_id, arm, number):
            made.append((case_id, arm, number))
            r.runs.append({"host": host, "skill": skill, "case": case_id, "arm": arm, "number": number,
                           "key": f"{case_id}-{arm}-{number}", "status": "made", "bundle": None})
            return r.runs[-1]

        def decide(*args):
            self.assertEqual(len(args[5]["extra runs"]["outcome"]["passes"]), len(found) - len(decisions))
            return decisions.pop(0)

        planted = mock.Mock(side_effect=AssertionError("the fault gate's runs are never extended"))
        with mock.patch.object(gates, "run_one", run_one), mock.patch.object(gates, "check_one", lambda r, m: {}), \
                mock.patch.object(gates, "pinned_stop", lambda r, m: None), mock.patch.object(faults, "run", planted), \
                mock.patch.object(grades, "grade", lambda r, m, f: {"runs": [], "goldens": {}}), \
                mock.patch.object(labels, "labels", decide), mock.patch.object(prices, "load", lambda repo: {}):
            outcome = extras.extra_gate(r)
        return made, outcome, decisions

    def test_a_clean_round_adds_no_runs(self):
        made, outcome, _ = self.round(6, label(**{"task pass rate": verdict("pass", with_skill=["c1"])}))
        self.assertEqual((made, outcome), ([], {"passes": []}))

    def test_extra_runs_0_or_none_named_adds_none(self):
        close = label(**{"task pass rate": verdict("too close", with_skill=["c1"])})
        for extra in (0, None):
            with self.subTest(extra=extra):
                made, outcome, left = self.round(extra, close)
                self.assertEqual((made, outcome, left), ([], {"passes": []}, [close]))  # never even decided

    def test_three_runs_go_to_each_split_case_only_in_the_arms_it_reads_and_the_cap_holds(self):
        close = label(**{"task pass rate": verdict("too close", with_skill=["c2"]),
                         "lift": verdict("pass", with_skill=["c1"], without_skill=[])})
        made, outcome, _ = self.round(6, close, close)  # still too close after both passes: the cap stops it
        self.assertEqual(made, [("c2", "with_skill", n) for n in range(4, 10)])
        self.assertEqual([len(found["runs"]) for found in outcome["passes"]], [3, 3])
        made, outcome, left = self.round(3, close, close)
        self.assertEqual((made, len(outcome["passes"]), len(left)), ([("c2", "with_skill", n) for n in (4, 5, 6)],
                                                                     1, 1))

    def test_a_pass_that_settles_every_verdict_ends_the_extra_runs(self):
        close = label(**{"lift": verdict("too close", with_skill=["c1"], without_skill=["c1"])})
        made, outcome, _ = self.round(6, close, label(**{"lift": verdict("pass", with_skill=["c1"],
                                                                          without_skill=["c1"])}))
        self.assertEqual(sorted(made), sorted((case, arm, n) for case, arm in (("c1", "with_skill"),
                                                                               ("c1", "without_skill"))
                                              for n in (4, 5, 6)))
        self.assertEqual(len(outcome["passes"]), 1)


class Labelled(TempCase):
    def test_the_label_reads_every_extra_run_and_names_them_per_case_and_arm(self):
        extra = [{"host": "h", "skill": "s", "case": "c1", "arm": arm, "number": n, "key": f"{arm}{n}"}
                 for arm in ("with_skill", "without_skill") for n in (4, 5, 6)]
        found = {"run": {"passed": True, "outcome": [{"key": "k1"}]},
                 "grade": {"passed": True, "outcome": {"runs": [{"key": "k1"}], "goldens": {"s/c1": {"q2": None}}}},
                 "extra runs": {"passed": True, "outcome": {"passes": [
                     {"runs": extra, "grades": [{"key": "with_skill4"}], "goldens": {"s/c1": {"q2": "missed"}}}]}}}
        merged = labels._with_extras(found)
        self.assertEqual([m["key"] for m in merged["run"]["outcome"]], ["k1"] + [m["key"] for m in extra])
        self.assertEqual(merged["grade"]["outcome"]["goldens"], {"s/c1": {"q2": "missed"}})  # any pass's doubt counts
        self.assertEqual(len(merged["grade"]["outcome"]["runs"]), 2)
        self.assertEqual([(m["case"], m["arm"], n) for m, n in labels._added(found, "h", "s")],
                         [("c1", "with_skill", 3), ("c1", "without_skill", 3)])
