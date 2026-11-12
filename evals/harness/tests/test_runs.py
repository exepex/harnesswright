"""The runs of a round: each is named by the hash of its inputs, stored once outside the working tree, kept when a
round resumes, and void, then remade, only for a harness fault."""

import json
import os
import shutil
import subprocess
import unittest

from helpers import TempCase
from test_gate import Upstream
from test_host import FAKE

import contain
import evidence
import rounds
import runs
from cases import Case

JAIL = contain.available()
VERSION = {"path": "/usr/bin/fakehost", "sha256": "0" * 64, "version": "fakehost 1.0"}
WROTE = json.dumps([{"do": "write", "path": "poem.md", "text": "An old silent pond\n"}, {"do": "say", "text": "Done."}])
DRIFT = {"own files": {"task": [], "trigger": []}}


class Round(TempCase):
    """A repository with one skill and one case, its round's manifest, and a store outside it."""

    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "repo"
        skill = self.repo / "skills" / "haiku-writer"
        skill.mkdir(parents=True)
        skill.joinpath("SKILL.md").write_text("---\nname: haiku-writer\ndescription: Writes a haiku. Use when asked "
                                              "for a haiku.\n---\n\n# Haiku writer\n")
        self.case_dir = self.repo / "evals" / "skills" / "haiku-writer" / "cases" / "c1"
        (self.case_dir / "world").mkdir(parents=True)
        (self.case_dir / "world" / "README.md").write_text("# Notes app\n")
        self.prompt(WROTE)
        (self.repo / "evals" / "harness").mkdir(parents=True)
        (self.repo / "evals" / "harness" / "cases.py").write_text("PLAIN = True\n")
        (self.repo / "evals" / "faults").mkdir()
        (self.repo / "evals" / "faults" / "harness.json").write_text('{"faults": []}\n')
        (self.repo / "evals" / "kit.json").write_text(json.dumps({"parts": {"fault catalogue": ["evals/faults"]}}))
        shutil.copytree(FAKE, self.repo / "adapters" / "fakehost", ignore=shutil.ignore_patterns("__pycache__"))
        self.store = self.tmp / "store"

    def prompt(self, text):
        (self.case_dir / "case.json").write_text(json.dumps({"prompt": text, "kind": "task"}))

    def plan(self, runs_per_arm=2):
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@example.invalid")
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "--allow-empty", "-m", "state"]):
            subprocess.run(["git", *args], cwd=self.repo, env=env, check=True, capture_output=True)
        path = self.tmp / "plan.json"
        path.write_text(json.dumps({"round": "r1", "skills": {"haiku-writer": ["c1"]}, "runs": runs_per_arm,
                                    "hosts": [{"adapter": "fakehost", "model": "named-model"}]}))
        return rounds.plan(path, repo=self.repo, adapters=self.repo / "adapters", version=lambda m, **c: VERSION)


class Keys(Round):
    def test_a_key_is_the_hash_of_every_input_of_the_run(self):
        record = self.plan()
        first = runs.key(record, "haiku-writer", "c1", "with_skill", "fakehost", 1)
        self.assertEqual(first, runs.key(record, "haiku-writer", "c1", "with_skill", "fakehost", 1))
        others = {runs.key(record, "haiku-writer", "c1", "without_skill", "fakehost", 1),
                  runs.key(record, "haiku-writer", "c1", "with_skill", "fakehost", 2),
                  runs.key(record, "haiku-writer", "c1", "with_skill", "fakehost", 1, code="1" * 64)}
        changed = json.loads(json.dumps(record))
        changed["hosts"]["fakehost"]["version"]["version"] = "fakehost 1.1"
        others.add(runs.key(changed, "haiku-writer", "c1", "with_skill", "fakehost", 1))
        changed = json.loads(json.dumps(record))
        changed["cases"]["haiku-writer"]["c1"] = "2" * 64
        others.add(runs.key(changed, "haiku-writer", "c1", "with_skill", "fakehost", 1))
        self.assertEqual(len(others), 5)
        self.assertNotIn(first, others)

    def test_the_skill_and_case_under_test_are_part_of_the_key(self):
        record = self.plan()
        twin = json.loads(json.dumps(record))
        twin["cases"]["limerick-writer"] = {"c2": record["cases"]["haiku-writer"]["c1"]}  # the same bytes
        self.assertNotEqual(runs.key(record, "haiku-writer", "c1", "with_skill", "fakehost", 1),
                            runs.key(twin, "limerick-writer", "c2", "with_skill", "fakehost", 1))

    def test_a_run_the_round_does_not_plan_has_no_key(self):
        record = self.plan()
        for args in (("haiku-writer", "c1", "previous", "fakehost", 1), ("haiku-writer", "c9", "with_skill",
                     "fakehost", 1), ("haiku-writer", "c1", "with_skill", "other", 1),
                     ("haiku-writer", "c1", "with_skill", "fakehost", 3), ("haiku-writer", "c1", "with_skill",
                     "fakehost", 0)):
            with self.subTest(args=args), self.assertRaises(runs.RunError):
                runs.key(record, *args)

    def test_the_runner_code_is_hashed_from_its_files(self):
        copy = self.tmp / "harness"
        copy.mkdir()
        for name in runs.RUNNER:
            shutil.copy2(runs.HARNESS / name, copy / name)
        self.assertEqual(runs.runner(copy), runs.runner())
        (copy / "evidence.py").write_text((copy / "evidence.py").read_text() + "# changed\n")
        self.assertNotEqual(runs.runner(copy), runs.runner())


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Runs(Round):
    def setUp(self):
        super().setUp()
        self.upstream = Upstream()
        self.addCleanup(self.upstream.close)
        self.tool = self.tmp / "tool"
        shutil.copytree(FAKE, self.tool, ignore=shutil.ignore_patterns("adapter.py", "__pycache__"))
        self.adapter = rounds.adapter("fakehost", self.repo / "adapters")

    def run_one(self, record, arm="with_skill", number=1, version=VERSION):
        return runs.run(record, self.store, Case(self.case_dir, "haiku-writer"), arm, "fakehost", number,
                        self.adapter, DRIFT, version, repo=self.repo, timeout=120,
                        operator_env={"PATH": f"{self.tool}:/usr/bin:/bin", "HTTPS_PROXY": self.upstream.url},
                        operator_home=self.tmp / "operator", host_paths=[self.tool])

    def test_a_run_is_made_once_and_kept_when_the_round_resumes(self):
        record = self.plan()
        made = self.run_one(record)
        self.assertEqual(made["status"], "made")
        bundle, _ = evidence.load(made["bundle"])
        self.assertEqual((bundle["arm"], bundle["model"], bundle["host_version"]),
                         ("with_skill", "named-model", "fakehost 1.0"))
        self.assertIn("poem.md", bundle["diff"])
        self.assertEqual(self.run_one(record), {**made, "status": "kept"})
        folder = self.store / "r1" / "runs" / made["key"]
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["bundle"])

    def test_each_arm_and_number_is_its_own_run(self):
        record = self.plan()
        keys = {self.run_one(record, arm, number)["key"] for arm in runs.ARMS for number in (1, 2)}
        self.assertEqual(len(keys), 4)
        self.assertEqual(len(list((self.store / "r1" / "runs").iterdir())), 4)

    def test_a_host_that_fails_voids_the_run_and_a_resumed_round_makes_it_again(self):
        self.prompt("not a list of actions")
        record = self.plan()
        void = self.run_one(record)
        self.assertEqual(void["status"], "void")
        self.assertIn("the host failed", void["reason"])
        self.assertEqual(runs.stored(self.store / "r1" / "runs" / void["key"])[0], "void")
        again = self.run_one(record)  # one remake, not kept
        self.assertEqual(again["status"], "void")
        self.assertEqual(len(runs.stored(self.store / "r1" / "runs" / void["key"])[1]), 2)
        empty = self.run_one(record)  # voided twice, the slot stays empty and is not run again
        self.assertEqual(empty["status"], "empty")
        self.assertIn("the host failed", empty["reason"])

    def test_a_repository_that_moved_on_from_the_round_commit_is_refused(self):
        record = self.plan()
        (self.repo / "skills" / "haiku-writer" / "SKILL.md").write_text("---\nname: haiku-writer\ndescription: "
                                                                         "Changed. Use when asked.\n---\n")
        with self.assertRaisesRegex(rounds.RoundError, "clean tree"):
            self.run_one(record)
        self.plan()  # committed: a new commit, not the round's
        with self.assertRaisesRegex(runs.RunError, "not at round r1's commit"):
            self.run_one(record)

    def test_a_remade_slot_keeps_its_void_for_the_void_rate(self):
        record = self.plan()
        void = self.run_one(record, version={**VERSION, "version": "fakehost 2.0"})
        made = self.run_one(record)
        self.assertEqual((void["key"], made["status"]), (made["key"], "made"))
        folder = self.store / "r1" / "runs" / made["key"]
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["bundle", "void.json"])
        self.assertEqual(len(json.loads((folder / "void.json").read_text())["reasons"]), 1)

    def test_a_host_whose_version_changed_is_void_and_never_run(self):
        record = self.plan()
        void = self.run_one(record, version={**VERSION, "version": "fakehost 2.0"})
        self.assertEqual(void["status"], "void")
        self.assertIn("is not the manifest's", void["reason"])
        self.assertFalse((self.store / "r1" / "runs" / void["key"] / "bundle").exists())

    def test_a_run_slot_linked_into_the_working_tree_is_refused(self):
        record = self.plan()
        slot = self.store / "r1" / "runs" / runs.key(record, "haiku-writer", "c1", "with_skill", "fakehost", 1)
        slot.parent.mkdir(parents=True)
        slot.symlink_to(self.repo)
        with self.assertRaisesRegex(runs.RunError, "outside the working tree"):
            self.run_one(record, version={**VERSION, "version": "fakehost 2.0"})
        self.assertFalse((self.repo / "void.json").exists())

    def test_a_store_inside_the_working_tree_is_refused(self):
        record = self.plan()
        self.store = self.repo / "store"
        with self.assertRaisesRegex(runs.RunError, "outside the working tree"):
            self.run_one(record)


if __name__ == "__main__":
    unittest.main()
