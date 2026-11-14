"""The label gate: the labels of 10 · Skills, every number read from what the round stored."""

import json
import tempfile
import types
import unittest

from test_gates import JUDGED
from test_grades import HELLO, POND, Pages, answering, pond, wrote
from test_prices import PRICES
from test_runs import DRIFT

import cases
import evidence
import gates
import grader
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


DRAFT = "A first draft\n"


def done_or_pond(adapter, page, asked, model=None, timeout=None, **containment):
    """A stand-in grader: q4, the done question, is yes unless the page is a draft; every other question is yes
    only for the haiku."""
    quote = page.splitlines()[0]
    answers = [{"id": q["id"], "answer": ("no" if DRAFT.strip() in page else "yes") if q["id"] == "q4"
                else pond(page), "evidence": quote} for q in asked]
    return grader.Graded({"answers": answers}, [], [[]])


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

    def test_a_trigger_run_passes_when_the_skill_loaded_exactly_when_it_should_an_inferred_load_named(self):
        def load(name, source="observed"):
            return [{"kind": "skill", "source": source, "name": name}]

        should, should_not = case("trigger", should_trigger=True), case("trigger", should_trigger=False)
        self.assertEqual(labels.trigger_outcome(should, load("haiku-writer")), (True, False))
        self.assertEqual(labels.trigger_outcome(should, load("other-skill")), (False, False))
        self.assertEqual(labels.trigger_outcome(should_not, load("other-skill")), (True, False))
        self.assertEqual(labels.trigger_outcome(should_not, load("haiku-writer")), (False, False))
        self.assertEqual(labels.trigger_outcome(should, load("haiku-writer", "inferred")), (True, True))
        self.assertEqual(labels.trigger_outcome(should_not, load("haiku-writer", "inferred")), (False, True))
        both = load("haiku-writer", "inferred") + load("haiku-writer")
        self.assertEqual(labels.trigger_outcome(should, both), (True, False))


def measured(task=(1, 1, 1), baseline=(0, 0, 0), trigger=(1, 1, 1), train=None, should=True):
    cases = {"t": case(), "g": case("trigger", should_trigger=should, split="test")}
    scored = {("t", "with_skill"): [bool(o) for o in task], ("t", "without_skill"): [bool(o) for o in baseline],
              ("g", "with_skill"): [bool(o) for o in trigger]}
    if train is not None:
        cases["x"] = case("trigger", should_trigger=True, split="train")
        scored[("x", "with_skill")] = train
    return labels.summary(cases, scored)


def against(task=(1, 1, 1), before=(1, 1, 0), done=(0, 3), done_before=(0, 3)):
    """The measures of a skill whose round ran a previous version, and the false-done tally of each arm."""
    cases = {"t": case(), "g": case("trigger", should_trigger=True, split="test")}
    scored = {("t", "with_skill"): [bool(o) for o in task], ("t", "without_skill"): [False] * 3,
              ("t", "previous_version"): [bool(o) for o in before], ("g", "with_skill"): [True] * 3}
    tally = {arm: {"false_done": f, "decided": d, "undecided": 0}
             for arm, (f, d) in (("with_skill", done), ("previous_version", done_before))}
    return labels.summary(cases, scored, previous=True), tally


class Previous(unittest.TestCase):
    def test_a_skill_at_least_as_good_as_its_previous_version_is_verified(self):
        found, tally = against()
        self.assertEqual((found["previous_pass_rate"], found["runs"]["t, previous_version"]), (0.6667, 3))
        self.assertEqual(labels.decide(found, [], false_done=tally), {"label": "verified", "gaps": []})
        found, tally = against(before=(1, 1, 1))  # equal is at least as good
        self.assertEqual(labels.decide(found, [], false_done=tally), {"label": "verified", "gaps": []})

    def test_a_skill_worse_than_its_previous_version_is_unsupported_with_each_gap_named(self):
        found, tally = against(task=(1,) * 9 + (0,), before=(1,) * 10, done=(1, 10), done_before=(0, 10))
        self.assertEqual(labels.decide(found, [], false_done=tally), {"label": "unsupported", "gaps": [
            "task pass rate 90% below the previous version's 100%",
            "false-done rate 1 of 10 above the previous version's 0 of 10"]})

    def test_too_few_previous_runs_or_no_decided_false_done_keep_the_label_inconclusive(self):
        found, tally = against(before=(1, 1))
        self.assertEqual(labels.decide(found, [], false_done=tally),
                         {"label": "inconclusive", "gaps": ["t, previous_version: 2 scored run(s), 3 needed"]})
        found, tally = against(done_before=(0, 0))
        self.assertEqual(labels.decide(found, [], false_done=tally)["gaps"],
                         ["false-done rate: no decided run in the with-skill or the previous version's arm"])

    def test_a_round_with_no_previous_version_is_decided_as_before(self):
        self.assertNotIn("previous_pass_rate", measured())
        self.assertNotIn("t, previous_version", measured()["runs"])


class Decide(unittest.TestCase):
    def test_enough_runs_meeting_every_threshold_with_lift_are_verified(self):
        found = measured(train=[False] * 3)  # the train split is for tuning: it does not count
        self.assertEqual((found["task_pass_rate"], found["baseline_pass_rate"], found["lift"]), (1.0, 0.0, 1.0))
        self.assertEqual((found["trigger_accuracy"], found["trigger_cases"]), (1.0, 1))
        self.assertEqual(labels.decide(found, []), {"label": "verified", "gaps": []})
        self.assertEqual(labels.decide(found, [], measured(), None), {"label": "verified", "gaps": []})

    def test_a_trigger_case_passes_on_half_its_runs_only_when_it_should_trigger(self):
        self.assertEqual(measured(trigger=(1, 1, 0, 0))["trigger_accuracy"], 1.0)
        self.assertEqual(measured(trigger=(1, 1, 0, 0), should=False)["trigger_accuracy"], 0.0)  # loaded twice of 4

    def test_a_skill_with_no_task_case_or_no_test_trigger_case_is_incomplete_with_every_doubt_named(self):
        no_triggers = labels.summary({"t": case()}, {("t", "with_skill"): [True] * 3,
                                                     ("t", "without_skill"): [False] * 3})
        self.assertEqual(labels.decide(no_triggers, ["t, with_skill, run 4: not scored (void)"]),
                         {"label": "incomplete", "gaps": ["test trigger cases: none",
                                                          "t, with_skill, run 4: not scored (void)"]})

    def test_every_doubt_is_named_and_keeps_the_label_inconclusive(self):
        found = labels.decide(measured(task=(1, 1)), [])
        self.assertEqual(found, {"label": "inconclusive", "gaps": ["t, with_skill: 2 scored run(s), 3 needed"]})
        self.assertEqual(labels.decide(measured(trigger=()), [])["gaps"], ["g, with_skill: 0 scored run(s), 3 needed"])
        unscored = ["t, with_skill, run 4: not scored (expectation 2 has no trusted answer)",
                    "t, with_skill, run 5: not scored (empty)", "haiku-writer/t q2: goldens missed (planted)"]
        self.assertEqual(labels.decide(measured(), unscored), {"label": "inconclusive", "gaps": unscored})
        self.assertIn("no lift", labels.decide(measured(baseline=(1, 1, 1)), [])["gaps"][0])

    def test_another_host_is_never_verified_on_a_reference_result_that_is_not_settled(self):
        found = labels.decide(measured(), [], None, "the reference host claude-code's result is not settled")
        self.assertEqual(found, {"label": "inconclusive",
                                 "gaps": ["the reference host claude-code's result is not settled"]})

    def test_a_missed_threshold_is_unsupported_with_each_gap_named(self):
        found = labels.decide(measured(task=(1, 1, 0), trigger=(0, 0, 1)), [], measured(), None)
        self.assertEqual(found["label"], "unsupported")
        self.assertEqual(found["gaps"], ["task pass rate 67% below 90%", "task pass rate 33% below the reference host",
                                         "trigger accuracy 0% below 90%"])


class Gate(Pages):
    """The label gate after the run, check and grade gates, on runs stored as a round stores them."""

    def setUp(self):
        super().setUp()
        (self.case_dir / "case.json").write_text(json.dumps({"prompt": "Write a haiku.", "kind": "task",
                                                             "expectations": EXPECTATIONS}))
        # q2 asks for the haiku, and q4, the done question, whether the run says it is done: the "no" golden wrote
        # the wrong poem and says it is done, a false done; the "draft" golden says it is not done
        for name, poem, answer, done in (("yes", POND, "yes", "yes"), ("no", HELLO, "no", "yes"),
                                         ("draft", DRAFT, "no", "no")):
            data = wrote(poem)
            data["settled"] = {f"q{n}": {"expectation": e["text"], "sha256": goldens.fingerprint(e), "answer": a,
                                         "by": "judge-a"}
                               for n, (e, a) in enumerate(zip([*EXPECTATIONS, cases.done()],
                                                              ["yes", answer, "yes", done]), start=1)}
            self.golden(name, data)
        (self.repo / "evals" / "results").mkdir(parents=True, exist_ok=True)
        (self.repo / "evals" / "results" / "prices.json").write_text(json.dumps(PRICES))

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
        outcome = self.go(steps, grade=done_or_pond)["gates"][-1]["outcome"]
        self.assertEqual(outcome, {"haiku-writer": {"fakehost": "incomplete"}})  # the case has no trigger case
        [path] = (self.store / "r1" / "labels").iterdir()
        found = json.loads(path.read_text())
        entry = found["skills"]["haiku-writer"]["fakehost"]
        self.assertEqual((entry["task_pass_rate"], entry["baseline_pass_rate"], entry["lift"]), (1.0, 0.0, 1.0))
        self.assertEqual((entry["runs"], entry["inferred_loads"]), ({"c1, with_skill": 3, "c1, without_skill": 3}, 0))
        self.assertEqual((entry["model"], entry["gaps"]), ("named-model", [
            "test trigger cases: none", "the reference host claude-code was not run"]))
        self.assertEqual(path.stem, found["attempt"])
        self.assertEqual((found["prices"], entry["faults"], entry["void_rate"]["with_skill"]["tries"]),
                         (PRICES["date"], None, 3))  # no fault gate here
        self.assertEqual(entry["golden_accuracy"], {"rate": 1.0, "right": 6, "asked": 6})  # q2 and q4 of 3 goldens
        # every run without the skill wrote the wrong poem and said it was done; every run with it was right
        self.assertEqual(entry["false_done"], {
            "with_skill": {"rate": 0.0, "false_done": 0, "decided": 3, "undecided": 0},
            "without_skill": {"rate": 1.0, "false_done": 3, "decided": 3, "undecided": 0}})
        self.assertEqual({arm: (c["runs"], c["money"], c["uncounted"]) for arm, c in entry["cost"].items()},
                         {"with_skill": (3, None, 3), "without_skill": (3, None, 3)})  # the fake host counts none

    def test_a_run_not_scored_and_the_goldens_missed_are_named(self):
        self.planned()
        probe, run = self.stored([("with_skill", POND)])
        steps = (("probe", probe), ("run", run), ("check", gates.check_gate), ("grade", grades.grade_gate),
                 ("label", labels.label_gate))
        self.go(steps, grade=answering(lambda page: "yes"))  # the "no" golden is missed: q2 is untrusted
        [path] = (self.store / "r1" / "labels").iterdir()
        found = json.loads(path.read_text())
        gaps = found["skills"]["haiku-writer"]["fakehost"]["gaps"]
        self.assertIn("c1, with_skill, run 1: not scored (expectation 2 has no trusted answer)", gaps)
        self.assertIn("c1, with_skill: 0 scored run(s), 3 needed", gaps)
        self.assertTrue(any(gap.startswith("haiku-writer/c1 q2: goldens missed") for gap in gaps))
        self.assertEqual(found["skills"]["haiku-writer"]["fakehost"]["false_done"], {
            "with_skill": {"rate": None, "false_done": 0, "decided": 0, "undecided": 1}})  # neither is trusted


if __name__ == "__main__":
    unittest.main()
