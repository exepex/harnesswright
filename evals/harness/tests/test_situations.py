"""Pressure situations (doc 11): a task case names the pressure it puts on the agent, the manifest records each
skill's situations, a case a plain agent cannot fail runs with the skill only, and the label holds every situation
to its own floor, reports it apart and names each situation the skill's list needs and no case covers."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from test_gates import Gated
from test_labels import case, formatted
from test_runs import DRIFT, VERSION

import cases
import faults
import gates
import labels
import rounds
import runs
from cases import ARMS

BOTH = {"haiku-writer": ["c1", "s1"]}
EVERY = list(cases.SITUATIONS)


def listed(applies=EVERY, **left_out):
    return {"haiku-writer": {"applies": applies, "left_out": left_out}}


class Plan(Gated):
    def situated(self, situation, case_id="s1"):
        folder = self.repo / "evals" / "skills" / "haiku-writer" / "cases" / case_id
        shutil.copytree(self.case_dir, folder)
        (folder / "case.json").write_text(json.dumps({"prompt": "Write a haiku about rain.", "kind": "task",
                                                      "situation": situation}))

    def listing(self, data):
        (self.repo / "evals" / "situations.json").write_text(json.dumps(data))

    def test_the_manifest_records_the_list_and_each_case_s_situation(self):
        self.situated("self-judge")
        self.listing(listed(["self-judge"], **{s: "not this skill's" for s in EVERY if s != "self-judge"}))
        record = self.plan(skills=BOTH)
        self.assertEqual(record["situations"], {"haiku-writer": {"listed": ["self-judge"],
                                                                 "cases": {"s1": "self-judge"}}})
        both = cases.Case(self.repo / "evals" / "skills" / "haiku-writer" / "cases" / "s1", "haiku-writer")
        self.assertEqual(runs.arms(record, both), ARMS)

    def test_a_skill_the_list_does_not_name_is_recorded_as_not_listed(self):
        self.assertEqual(self.plan()["situations"], {"haiku-writer": {"listed": None, "cases": {}}})

    def test_a_case_a_plain_agent_cannot_fail_runs_with_the_skill_only(self):
        self.situated("check-cannot-run")
        record = self.plan(skills=BOTH)
        rounds.write(record, self.store, self.repo)
        alone = cases.Case(self.repo / "evals" / "skills" / "haiku-writer" / "cases" / "s1", "haiku-writer")
        self.assertEqual(runs.arms(record, alone), ARMS[1:])
        self.assertEqual(runs.arms(record, cases.Case(self.case_dir, "haiku-writer")), ARMS)
        with self.assertRaisesRegex(runs.RunError, "not a run of round"):
            runs.key(record, "haiku-writer", "s1", ARMS[0], "fakehost", 1, DRIFT)
        self.assertEqual(len(runs.key(record, "haiku-writer", "s1", ARMS[1], "fakehost", 1, DRIFT)), 64)
        planned = {("haiku-writer", i): SimpleNamespace(kind="task", skill="haiku-writer", id=i) for i in ("c1", "s1")}
        self.assertEqual({arm for _, _, i, arm, _ in gates.order(record, ["fakehost"], planned) if i == "s1"},
                         {ARMS[1]})

    def test_the_fault_gate_never_plants_on_a_case_with_one_arm(self):
        self.situated("check-cannot-run")
        with self.assertRaisesRegex(rounds.RoundError, "fault_case runs with the skill only"):
            self.plan(skills=BOTH, fault_case={"skill": "haiku-writer", "case": "s1"})
        rounds.write(self.plan(skills=BOTH), self.store, self.repo)
        planted = []

        def run(entry, setup, seed):
            planted.append(setup.case.id)
            return {"id": entry["id"], "place": "plant", "caught": True, "reason": "", "seen": [], "bundles": []}

        def probed(r):
            r.hosts["fakehost"] = {"drift": DRIFT}

        with mock.patch.object(faults, "run", run), mock.patch.object(faults, "load", return_value=[{"id": "f"}] * 4):
            self.go((("probe", probed), ("faults", gates.faults_gate)), version=lambda module, **c: VERSION)
        self.assertEqual(set(planted), {"c1"})

    def test_a_skill_with_no_folder_yet_cannot_run_a_case_with_the_skill_only(self):
        self.situated("check-cannot-run")
        shutil.rmtree(self.repo / "skills" / "haiku-writer")
        with self.assertRaisesRegex(rounds.RoundError, "runs task cases without it only"):
            self.plan(skills=BOTH, fault_case={"skill": "haiku-writer", "case": "c1"})


class Fields(unittest.TestCase):
    def test_a_situation_is_one_of_the_list_and_only_for_task_cases(self):
        task = {"prompt": "Write.", "kind": "task"}
        trigger = {"prompt": "Write.", "kind": "trigger", "should_trigger": True, "split": "test",
                   "index": {"file": "INDEX", "after": "x", "row": "{name}"}}
        for data, problem in (({**task, "situation": "no-python"}, "situation must be one of"),
                              ({**trigger, "situation": "self-judge"}, "situation is only for task cases")):
            with self.subTest(problem), self.assertRaisesRegex(cases.CaseError, problem):
                cases.check(data, "s1")
        self.assertEqual(cases.check({**task, "situation": "self-judge"}, "s1")["situation"], "self-judge")

    def test_the_list_gives_every_situation_once_each_left_out_with_a_reason(self):
        path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "situations.json"
        self.assertEqual(cases.situations(path), {})  # no file: no skill is listed
        path.write_text(json.dumps(listed(EVERY[1:], **{EVERY[0]: "No such input."})))
        self.assertEqual(cases.situations(path), {"haiku-writer": sorted(EVERY[1:])})
        for wrong in (listed(EVERY[1:]), listed(EVERY, **{EVERY[0]: "Twice."}), listed(EVERY[1:], **{EVERY[0]: ""}),
                      listed(EVERY + ["no-python"]), {"Haiku": listed()["haiku-writer"]}):
            with self.subTest(wrong), self.assertRaisesRegex(cases.CaseError, "exactly one"):
                path.write_text(json.dumps(wrong))
                cases.situations(path)


def situated(scored, situation_of, listed_=None, plain="t"):
    """The label measures of one skill with `plain` task cases, each passing only with the skill, its situation cases
    by id with their `scored` runs, and a test trigger case."""
    own = {"g": case("trigger", should_trigger=True, split="test"), **{i: case() for i in [*plain, *situation_of]}}
    scored = {("g", "with_skill"): [True] * 3, **{(i, "with_skill"): [True] * 3 for i in plain},
              **{(i, "without_skill"): [False] * 3 for i in plain}, **scored}
    record = {"listed": sorted(set(situation_of.values())) if listed_ is None else listed_, "cases": situation_of}
    return {**labels.summary(own, scored, situations=record), **formatted()}


class Label(unittest.TestCase):
    def test_each_situation_is_reported_apart_and_one_with_the_skill_only_counts_in_no_rate(self):
        found = situated({("s", "with_skill"): [True] * 3, ("s", "without_skill"): [False] * 3,
                          ("x", "with_skill"): [True] * 3}, {"s": "self-judge", "x": "check-cannot-run"})
        self.assertEqual((found["task_pass_rate"], found["baseline_pass_rate"]), (1.0, 0.0))
        self.assertEqual(found["situations"], {
            "check-cannot-run": {"cases": ["x"], "with_skill": {"passed": 3, "runs": 3}},
            "none": {"cases": ["t"], "with_skill": {"passed": 3, "runs": 3},
                     "without_skill": {"passed": 0, "runs": 3}},
            "self-judge": {"cases": ["s"], "with_skill": {"passed": 3, "runs": 3},
                           "without_skill": {"passed": 0, "runs": 3}}})
        self.assertNotIn("x, without_skill", found["runs"])
        self.assertEqual(labels.decide(found, []), {"label": "verified", "gaps": []})
        alone = situated({("x", "with_skill"): [False] * 3}, {"x": "check-cannot-run"})
        self.assertEqual(alone["task_pass_rate"], 1.0)  # its failures stay out of the pooled rate, not the floor
        self.assertEqual(labels.decide(alone, [])["gaps"],
                         ["situation check-cannot-run: 3 of 3 with-skill runs failed"])

    def test_one_failed_with_skill_run_of_a_situation_is_unsupported_though_the_pool_passes(self):
        found = situated({("s", "with_skill"): [True, True, False], ("s", "without_skill"): [False] * 3},
                         {"s": "self-judge"}, plain="abcdefhi")  # 26 of 27 with-skill runs pass
        self.assertGreater(found["task_pass_rate"], labels.THRESHOLDS["task_pass_rate"])
        self.assertEqual(labels.decide(found, []), {"label": "unsupported", "gaps": [
            "situation self-judge: 1 of 3 with-skill runs failed"]})

    def test_a_listed_situation_with_no_case_or_a_skill_not_listed_is_incomplete_and_named(self):
        found = situated({}, {}, ["self-judge", "stale-evidence"])
        self.assertEqual(labels.decide(found, [])["label"], "incomplete")
        self.assertEqual(labels.decide(found, [])["gaps"], ["situation self-judge: no case",
                                                            "situation stale-evidence: no case"])
        unlisted = {**situated({}, {}), "situations_listed": None}
        self.assertEqual(labels.decide(unlisted, []), {"label": "incomplete", "gaps": [
            "situations: the skill is not in evals/situations.json"]})


if __name__ == "__main__":
    unittest.main()
