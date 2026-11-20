"""Skill kinds (doc 12, Skill kinds): one reader gives a skill's kind from a kit part, a plan cannot set it, an
internal skill never runs without itself, and a round of internal skills plants its faults on a team skill's case."""

import hashlib
import json
import shutil
import types

from helpers import TempCase
from test_runs import DRIFT, Round

import cases
import kit
import rounds
import runs
import setups
from cases import REPO


class Reader(TempCase):
    def test_the_kinds_file_gives_each_skill_team_or_internal_and_nothing_else(self):
        self.assertEqual(cases.kinds(REPO / "evals" / "kinds.json"),
                         {"claims-writer": "team", "skill-designer": "internal"})
        path = self.tmp / "kinds.json"
        self.assertEqual(cases.kinds(path), {})  # no file: no skill has a kind, so every label is incomplete
        for wrong in ({"haiku-writer": "easy"}, ["haiku-writer"], {"Haiku": "team"}):
            with self.subTest(wrong=wrong), self.assertRaisesRegex(cases.CaseError, "team or internal"):
                path.write_text(json.dumps(wrong))
                cases.kinds(path)

    def test_the_kit_lists_harnesswright_s_own_checks_by_name_none_yet(self):
        self.assertEqual(cases.own_checks(cases.OWN_CHECK_FILE), [])
        self.assertIn("evals/own-checks.json", kit.parts()["checks"])
        path = self.tmp / "own-checks.json"
        self.assertEqual(cases.own_checks(path), [])  # no file: no check counts as harnesswright's own
        path.write_text(json.dumps(["release_check", "files", "files"]))
        self.assertEqual(cases.own_checks(path), ["files", "release_check"])
        for wrong in ("files", ["Files"], [1], {"files": True}):
            with self.subTest(wrong=wrong), self.assertRaisesRegex(cases.CaseError, "list of check names"):
                path.write_text(json.dumps(wrong))
                cases.own_checks(path)

    def test_the_kinds_and_the_label_rule_are_kit_parts_and_the_label_rule_is_one_list(self):
        parts = kit.parts()
        self.assertEqual(parts["kinds"], ["evals/kinds.json"])
        self.assertIn("evals/harness/verdicts.py", parts["label rule"])
        self.assertTrue({"evals/kinds.json", *parts["label rule"]} <= set(kit.files()))
        self.assertFalse(hasattr(setups, "LABEL_RULE"))  # the setup reads the kit's list, never a copy of it


class Planned(Round):
    def kinds(self, **declared):
        (self.repo / "evals" / "kinds.json").write_text(json.dumps(declared))

    def team_case(self):
        """limerick-writer, a held team skill with one task case, for the fault gate."""
        (self.repo / "skills" / "limerick-writer").mkdir()
        (self.repo / "skills" / "limerick-writer" / "SKILL.md").write_text(
            "---\nname: limerick-writer\ndescription: Writes a limerick. Use when asked for a limerick.\n---\n")
        shutil.copytree(self.case_dir, self.repo / "evals" / "skills" / "limerick-writer" / "cases" / "l1")
        return {"skill": "limerick-writer", "case": "l1"}

    def test_the_manifest_records_the_declared_kind_and_a_plan_cannot_set_one(self):
        self.assertEqual(self.plan()["kinds"], {"haiku-writer": None})  # undeclared: its label is incomplete
        self.kinds(**{"haiku-writer": "team"})
        with self.assertRaisesRegex(rounds.RoundError, "harness fault: .*not a release manifest"):
            self.plan()  # a team skill's release is proved when the round is planned, before any case runs
        skill = self.repo / "skills" / "haiku-writer" / "SKILL.md"
        (self.repo / "skills" / "manifest.json").write_text(json.dumps({
            "rulebook-version": "0.8.0", "run-time": ["manifest.json"], "run-time-files": {},
            "skills": {"haiku-writer": {"files": {"SKILL.md": hashlib.sha256(skill.read_bytes()).hexdigest()}}}}))
        record = self.plan()
        self.assertEqual((record["kinds"], record["release_proof"]),
                         ({"haiku-writer": "team"}, {"haiku-writer": {"with_skill": "hashes"}}))
        (self.repo / "evals" / "own-checks.json").write_text('["files"]')
        self.assertEqual(self.plan()["own_checks"], ["files"])  # the list an internal label reads, from the kit
        with self.assertRaisesRegex(rounds.RoundError, "kinds"):
            self.plan(kinds={"haiku-writer": "internal"})

    def test_an_internal_skill_runs_with_the_skill_and_its_previous_version_only(self):
        self.kinds(**{"haiku-writer": "internal", "limerick-writer": "team"})
        fault = self.team_case()
        record = self.plan(fault_case=fault)
        case = types.SimpleNamespace(skill="haiku-writer", id="c1", kind="task")
        self.assertEqual(runs.arms(record, case), ("with_skill",))
        self.assertEqual(runs.arms({**record, "previous": {"haiku-writer": {}}}, case), ("with_skill", runs.PREVIOUS))
        runs.key(record, "haiku-writer", "c1", "with_skill", "fakehost", 1, DRIFT)
        with self.assertRaisesRegex(runs.RunError, "not a run of round r1"):  # no without-skill run key
            runs.key(record, "haiku-writer", "c1", "without_skill", "fakehost", 1, DRIFT)
        team = types.SimpleNamespace(skill="limerick-writer", id="l1", kind="task")
        self.assertEqual(runs.arms({**record, "cases": {**record["cases"], "limerick-writer": {"l1": ""}}}, team),
                         runs.ARMS)

    def test_a_round_of_internal_skills_names_a_team_skill_s_case_for_its_faults(self):
        self.kinds(**{"haiku-writer": "internal", "limerick-writer": "team"})
        with self.assertRaisesRegex(rounds.RoundError, "no case of a skill with a folder runs in both arms"):
            self.plan()
        fault = self.team_case()
        self.assertEqual(self.plan(fault_case=fault)["fault_case"]["skill"], "limerick-writer")
        self.kinds(**{"haiku-writer": "internal", "limerick-writer": "internal"})
        with self.assertRaisesRegex(rounds.RoundError, "fault_case is a case of an internal skill"):
            self.plan(fault_case=fault)

    def test_an_internal_skill_with_no_folder_yet_is_refused(self):
        self.kinds(**{"haiku-writer": "internal"})
        shutil.rmtree(self.repo / "skills" / "haiku-writer")
        with self.assertRaisesRegex(rounds.RoundError, "haiku-writer is internal and has no folder yet"):
            self.plan()
