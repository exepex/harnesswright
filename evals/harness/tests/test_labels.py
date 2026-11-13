"""The label gate: the labels of 10 · Skills, every number read from what the round stored."""

import json
import tempfile
import types
import unittest

from test_gates import JUDGED
from test_grades import HELLO, POND, Pages, answering, pond, wrote
from test_runs import DRIFT

import evidence
import gates
import goldens
import grades
import labels

CONTRACT = {"contract": {"path": "README.md", "line": 1, "quote": "# Notes app"}}
EXPECTATIONS = [  # a format check, a contract question for the graders, and a contract check
    {"text": "The poem is written", "source": "format", "judged": JUDGED,
     "check": {"name": "file_state", "args": {"path": "poem.md", "state": "changed"}}},
    {"text": "The poem is a haiku", "source": CONTRACT, "judged": JUDGED},
    {"text": "The notes are kept", "source": CONTRACT, "judged": JUDGED,
     "check": {"name": "file_state", "args": {"path": "README.md", "state": "unchanged"}}},
]


def case(kind="task", expectations=EXPECTATIONS, **fields):
    return types.SimpleNamespace(skill="haiku-writer", kind=kind, expectations=expectations, **fields)


def verdict(outcome, name="file_state"):
    return {"check": name, "outcome": outcome, "reason": "planted"}


class Outcomes(unittest.TestCase):
    def test_a_task_run_counts_its_contract_expectations_a_check_first_then_a_trusted_answer(self):
        self.assertEqual(labels.task_outcome(case(), [verdict("fail"), None, verdict("pass")], {"q2": "yes"}),
                         (True, ""))  # the format check that failed does not count
        self.assertEqual(labels.task_outcome(case(), [verdict("pass"), None, verdict("pass")], {"q2": "no"}),
                         (False, "expectation 2 failed"))
        self.assertEqual(labels.task_outcome(case(), [verdict("pass"), None, verdict("undecidable")],
                                             {"q2": "yes", "q3": "no"}), (False, "expectation 3 failed"))
        self.assertEqual(labels.task_outcome(case(), [verdict("pass"), None, verdict("pass")], {}),
                         (None, "expectation 2 has no trusted answer"))  # untrusted or unanswered
        self.assertEqual(labels.task_outcome(case(), [verdict("pass"), None, verdict("fail")], {})[0], False)
        self.assertEqual(labels.task_outcome(case(expectations=EXPECTATIONS[:1]), [verdict("pass")], {}),
                         (None, "the case has no contract expectation"))

    def test_a_trigger_run_passes_when_the_skill_loaded_exactly_when_it_should(self):
        loaded = [{"kind": "skill", "source": "observed", "name": "haiku-writer"}]
        other = [{"kind": "skill", "source": "observed", "name": "other-skill"}]
        self.assertTrue(labels.trigger_outcome(case("trigger", should_trigger=True), loaded))
        self.assertFalse(labels.trigger_outcome(case("trigger", should_trigger=True), other))
        self.assertTrue(labels.trigger_outcome(case("trigger", should_trigger=False), other))
        self.assertFalse(labels.trigger_outcome(case("trigger", should_trigger=False), loaded))


def measured(task=(1, 1, 1), baseline=(0, 0, 0), trigger=(1, 1, 1), train=None):
    cases = {"t": case(), "g": case("trigger", should_trigger=True, split="test")}
    scored = {("t", "with_skill"): [bool(o) for o in task], ("t", "without_skill"): [bool(o) for o in baseline],
              ("g", "with_skill"): [bool(o) for o in trigger]}
    if train is not None:
        cases["x"] = case("trigger", should_trigger=True, split="train")
        scored[("x", "with_skill")] = train
    return labels.summary(cases, scored)


class Decide(unittest.TestCase):
    def decide(self, measures, reference=None, unreliable=None, reference_run=True):
        return labels.decide(measures, reference, unreliable or {}, reference_run)

    def test_enough_runs_meeting_every_threshold_with_lift_are_verified(self):
        found = measured(train=[False] * 3)  # the train split is for tuning: it does not count
        self.assertEqual((found["task_pass_rate"], found["baseline_pass_rate"], found["lift"]), (1.0, 0.0, 1.0))
        self.assertEqual((found["trigger_accuracy"], found["trigger_cases"]), (1.0, 1))
        self.assertEqual(self.decide(found), {"label": "verified", "gaps": []})

    def test_a_missing_result_is_incomplete(self):
        found = self.decide(measured(trigger=()))
        self.assertEqual(found, {"label": "incomplete", "gaps": ["g, with_skill: no scored run"]})
        no_triggers = labels.summary({"t": case()}, {("t", "with_skill"): [True] * 3,
                                                     ("t", "without_skill"): [False] * 3})
        self.assertEqual(self.decide(no_triggers)["gaps"], ["test trigger cases: none"])

    def test_too_few_runs_missed_goldens_no_lift_or_no_reference_host_are_inconclusive(self):
        self.assertEqual(self.decide(measured(task=(1, 1)))["gaps"], ["t, with_skill: 2 scored run(s), 3 needed"])
        found = self.decide(measured(), unreliable={"haiku-writer/c1 q2": "a golden was missed"})
        self.assertEqual(found, {"label": "inconclusive", "gaps": ["haiku-writer/c1 q2: goldens missed (a golden "
                                                                   "was missed)"]})
        self.assertIn("no lift", self.decide(measured(baseline=(1, 1, 1)))["gaps"][0])
        self.assertEqual(self.decide(measured(), reference_run=False)["label"], "inconclusive")
        found = labels.decide(measured(), None, {}, True, ["t, with_skill, run 4: empty"])
        self.assertEqual(found, {"label": "inconclusive", "gaps": ["t, with_skill, run 4: empty: not scored"]})

    def test_a_missed_threshold_is_unsupported_with_each_gap_named(self):
        found = self.decide(measured(task=(1, 1, 0), trigger=(0, 0, 1)), reference=measured())
        self.assertEqual(found["label"], "unsupported")
        self.assertEqual(found["gaps"], ["task pass rate 67% below 90%", "task pass rate 33% below the reference host",
                                         "trigger accuracy 0% below 90%"])


class Gate(Pages):
    """The label gate after the run, check and grade gates, on runs stored as a round stores them."""

    def setUp(self):
        super().setUp()
        (self.case_dir / "case.json").write_text(json.dumps({"prompt": "Write a haiku.", "kind": "task",
                                                             "expectations": EXPECTATIONS}))
        for name, poem, answer in (("yes", POND, "yes"), ("no", HELLO, "no")):
            data = wrote(poem)
            data["settled"] = {f"q{n}": {"expectation": e["text"], "sha256": goldens.fingerprint(e), "answer": a,
                                         "by": "judge-a"}
                               for n, (e, a) in enumerate(zip(EXPECTATIONS, ["yes", answer, "yes"]), start=1)}
            self.golden(name, data)

    def stored(self, poems):
        """A probe and run gate that give the fake host and one made run per (arm, poem) of `poems`."""
        def probe(r):
            r.hosts["fakehost"] = {"drift": DRIFT}
            return {"passed": ["fakehost"], "not run": {}, "drift": {}}

        def run(r):
            case_, made = r.cases[("haiku-writer", "c1")], []
            for number, (arm, poem) in enumerate(poems, start=1):
                out = tempfile.mkdtemp(dir=self.tmp)
                record, blobs = goldens.bundle(goldens.Golden("run", wrote(poem)), case_, r.modules["fakehost"],
                                               out, DRIFT, "fakehost 1.0", "named-model", self.repo / "skills")
                kept = self.store / "r1" / "runs" / f"k{number}" / "bundle"
                bundle = str(kept if kept.is_dir() else evidence.store(record, blobs, kept))
                made.append({"host": "fakehost", "skill": "haiku-writer", "case": "c1", "arm": arm, "number": number,
                             "key": f"k{number}", "status": "made"})
                r.runs.append({**made[-1], "bundle": bundle})
            return made
        return probe, run

    def test_the_label_file_counts_each_scored_run_and_names_what_is_missing(self):
        self.planned()
        probe, run = self.stored([("with_skill", POND)] * 3 + [("without_skill", HELLO)] * 3)
        steps = (("probe", probe), ("run", run), ("check", gates.check_gate), ("grade", grades.grade_gate),
                 ("label", labels.label_gate))
        outcome = self.go(steps, grade=answering(pond))["gates"][-1]["outcome"]
        self.assertEqual(outcome, {"haiku-writer": {"fakehost": "incomplete"}})  # the case has no trigger case
        [path] = (self.store / "r1" / "labels").iterdir()
        found = json.loads(path.read_text())
        entry = found["skills"]["haiku-writer"]["fakehost"]
        self.assertEqual((entry["task_pass_rate"], entry["baseline_pass_rate"], entry["lift"]), (1.0, 0.0, 1.0))
        self.assertEqual(entry["runs"], {"c1, with_skill": 3, "c1, without_skill": 3})
        self.assertEqual((entry["model"], entry["gaps"], found["ungraded"]), ("named-model",
                                                                              ["test trigger cases: none"], []))
        self.assertEqual(path.stem, found["attempt"])

    def test_a_run_ungraded_on_a_contract_question_is_left_out_and_named(self):
        self.planned()
        probe, run = self.stored([("with_skill", POND)])
        steps = (("probe", probe), ("run", run), ("check", gates.check_gate), ("grade", grades.grade_gate),
                 ("label", labels.label_gate))
        self.go(steps, grade=answering(lambda page: "yes"))  # the "no" golden is missed: q2 is untrusted
        [path] = (self.store / "r1" / "labels").iterdir()
        found = json.loads(path.read_text())
        self.assertEqual(found["ungraded"], [{"key": "k1", "why": "expectation 2 has no trusted answer"}])
        self.assertIn("c1, with_skill: no scored run", found["skills"]["haiku-writer"]["fakehost"]["gaps"])


if __name__ == "__main__":
    unittest.main()
