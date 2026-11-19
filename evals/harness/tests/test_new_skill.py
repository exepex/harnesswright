"""A new skill's first baseline round: a skill with cases but no folder yet runs without the skill only, is linted
in that arm, and the fault gate plants its faults on a case of a skill the repository holds."""

import json
import shutil
import unittest
from unittest import mock

from test_gates import Gated
from test_runs import DRIFT, VERSION

import faults
import gates
import rounds

NEW = {"haiku-writer": ["c1"], "limerick-writer": ["l1"]}


class NewSkill(Gated):
    def setUp(self):
        super().setUp()
        self.new = self.repo / "evals" / "skills" / "limerick-writer" / "cases" / "l1"
        shutil.copytree(self.case_dir, self.new)

    def planned_new(self, **extra):
        record = self.plan(**extra)
        rounds.write(record, self.store, self.repo)
        return record

    def test_the_lint_gate_lints_the_without_skill_arm_of_a_skill_with_no_folder(self):
        self.planned_new(skills=NEW)
        self.assertEqual(self.go(gates.GATES[1:2])["gates"][0]["outcome"], {"cases": 2, "hosts": 1})

    def test_the_lint_gate_still_stops_a_case_that_names_the_skill_with_no_folder(self):
        (self.new / "case.json").write_text(json.dumps({"prompt": "Use the limerick-writer skill.", "kind": "task"}))
        self.planned_new(skills=NEW)
        with self.assertRaisesRegex(rounds.RoundError, "stopped at the lint gate: fakehost, limerick-writer/l1: "):
            self.go(gates.GATES[1:2])

    def faults_planted_on(self, **extra):
        self.planned_new(**extra)
        planted = []

        def run(entry, setup, seed):
            planted.append((setup.case.skill, setup.case.id))
            return {"id": entry["id"], "place": "plant", "caught": True, "reason": "", "seen": [], "bundles": []}

        def probed(r):
            r.hosts["fakehost"] = {"drift": DRIFT}

        with mock.patch.object(faults, "run", run), mock.patch.object(faults, "load", return_value=[{"id": "f1"}]):
            self.go((("probe", probed), ("faults", gates.faults_gate)), version=lambda module, **c: VERSION)
        return planted

    def test_faults_are_planted_on_a_case_of_a_skill_the_repository_holds(self):
        self.assertEqual(self.faults_planted_on(skills=NEW), [("haiku-writer", "c1")])

    def test_faults_are_planted_on_the_plans_fault_case_when_every_skill_is_new(self):
        chosen = {"skill": "haiku-writer", "case": "c1"}
        self.assertEqual(self.faults_planted_on(skills={"limerick-writer": ["l1"]}, fault_case=chosen),
                         [("haiku-writer", "c1")])


if __name__ == "__main__":
    unittest.main()
