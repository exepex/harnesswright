"""Round plans: a plan holds only the fields of its schema, its manifest hashes every input it names, and a round's
manifest is written once, outside the working tree."""

import json
import os
import shutil
import subprocess
import unittest

from helpers import TempCase
from test_gate import Upstream
from test_host import FAKE

import contain
import rounds
from cases import REPO, Case

JAIL = contain.available()
PLAN = {"round": "r1", "skills": {"haiku-writer": ["c1"]}, "hosts": [{"adapter": "fakehost", "model": "named-model"}],
        "runs": 3}
VERSION = {"path": "/usr/bin/fakehost", "sha256": "0" * 64, "version": "fakehost 1.0"}


def stub(module, **containment):
    return dict(VERSION)


class Plans(TempCase):
    def write_plan(self, data=PLAN, name="plan.json"):
        path = self.tmp / name
        path.write_text(json.dumps(data))
        return path

    def test_a_plan_with_every_field_in_its_shape_is_read(self):
        self.assertEqual(rounds.read_plan(self.write_plan()), PLAN)

    def test_a_plan_may_name_a_previous_version_by_its_full_commit(self):
        data = {**PLAN, "previous": {"haiku-writer": "a" * 40}}
        self.assertEqual(rounds.read_plan(self.write_plan(data)), data)

    def test_a_plan_holds_exactly_its_fields_each_in_its_shape(self):
        wrong = {
            "an unknown field": {**PLAN, "store": "/tmp/x"},
            "a missing field": {k: v for k, v in PLAN.items() if k != "runs"},
            "no runs": {**PLAN, "runs": 0},
            "too many runs": {**PLAN, "runs": 21},
            "runs as text": {**PLAN, "runs": "3"},
            "runs as a bool": {**PLAN, "runs": True},
            "no skills": {**PLAN, "skills": {}},
            "a skill with no cases": {**PLAN, "skills": {"haiku-writer": []}},
            "a case named twice": {**PLAN, "skills": {"haiku-writer": ["c1", "c1"]}},
            "a case that is a path": {**PLAN, "skills": {"haiku-writer": ["../c1"]}},
            "no hosts": {**PLAN, "hosts": []},
            "a host named twice": {**PLAN, "hosts": PLAN["hosts"] * 2},
            "a host with no model": {**PLAN, "hosts": [{"adapter": "fakehost"}]},
            "an empty model": {**PLAN, "hosts": [{"adapter": "fakehost", "model": " "}]},
            "an unknown host field": {**PLAN, "hosts": [{**PLAN["hosts"][0], "sandbox": "off"}]},
            "an empty previous": {**PLAN, "previous": {}},
            "a short previous commit": {**PLAN, "previous": {"haiku-writer": "abc1234"}},
            "a previous for a skill not run": {**PLAN, "previous": {"limerick-writer": "a" * 40}},
        }
        for why, data in wrong.items():
            with self.subTest(why), self.assertRaises(rounds.RoundError):
                rounds.read_plan(self.write_plan(data))
        for text in ("[]", "not json", "\xff"):
            with self.subTest(text=text), self.assertRaises(rounds.RoundError):
                (self.tmp / "bad.json").write_bytes(text.encode("latin-1"))
                rounds.read_plan(self.tmp / "bad.json")


class Manifests(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "repo"
        self.skill_dir = self.repo / "skills" / "haiku-writer"
        self.skill_dir.mkdir(parents=True)
        self.skill_dir.joinpath("SKILL.md").write_text(
            "---\nname: haiku-writer\ndescription: Writes a haiku. Use when asked for a haiku.\nmetadata:\n"
            "  source: owner/repo@abc skills/haiku\n---\n\n# Haiku writer\n")
        self.world = self.repo / "evals" / "skills" / "haiku-writer" / "cases" / "c1" / "world"
        self.world.mkdir(parents=True)
        (self.world / "README.md").write_text("# Notes app\n")
        (self.world.parent / "case.json").write_text(json.dumps({"prompt": "Write a haiku.", "kind": "task"}))
        (self.repo / "evals" / "harness").mkdir(parents=True)
        (self.repo / "evals" / "harness" / "cases.py").write_text("PLAIN = True\n")
        (self.repo / "evals" / "faults").mkdir()
        (self.repo / "evals" / "faults" / "harness.json").write_text('{"faults": []}\n')
        (self.repo / "evals" / "kit.json").write_text(json.dumps({"parts": {"fault catalogue": ["evals/faults"]}}))
        self.adapters = self.repo / "adapters"
        shutil.copytree(FAKE, self.adapters / "fakehost", ignore=shutil.ignore_patterns("__pycache__"))
        self.commit()

    def commit(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@example.invalid")
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "state"]):
            subprocess.run(["git", *args], cwd=self.repo, env=env, check=True, capture_output=True)

    def plan(self, data=PLAN):
        path = self.tmp / "plan.json"
        path.write_text(json.dumps(data))
        return rounds.plan(path, repo=self.repo, adapters=self.adapters, version=stub)

    def test_the_manifest_hashes_every_input_the_plan_names(self):
        record = self.plan()
        self.assertEqual(record["round"], "r1")
        self.assertEqual(record["plan"], PLAN)
        self.assertEqual(record["cases"], {"haiku-writer": {"c1": Case(self.world.parent, "haiku-writer").sha256}})
        self.assertEqual(record["skills"]["haiku-writer"]["source"], "owner/repo@abc skills/haiku")
        self.assertEqual(len(record["skills"]["haiku-writer"]["sha256"]), 64)
        self.assertIsNone(record["skills"]["haiku-writer"]["upstream"])
        self.assertEqual(len(record["kit"]), 64)
        self.assertEqual(len(record["adapters"]["fakehost"]), 64)
        self.assertEqual(len(record["commit"]), 40)
        self.assertEqual(record["hosts"], {"fakehost": {"version": VERSION, "model": "named-model"}})

    def test_every_skill_an_arm_installs_and_its_upstream_copy_are_hashed(self):
        sibling = self.repo / "skills" / "limerick-writer"
        sibling.mkdir()
        sibling.joinpath("SKILL.md").write_text("---\nname: limerick-writer\ndescription: Writes a limerick. Use "
                                                "when asked for one.\n---\n\n# Limerick writer\n")
        (self.world.parent / "case.json").write_text(json.dumps({"prompt": "Write a haiku.", "kind": "task",
                                                                 "siblings": ["limerick-writer"]}))
        upstream = self.repo / "evals" / "skills" / "haiku-writer" / "upstream"
        upstream.mkdir()
        (upstream / "SKILL.md").write_text("# The source as borrowed\n")
        self.commit()
        before = self.plan()
        self.assertEqual(sorted(before["skills"]), ["haiku-writer", "limerick-writer"])
        self.assertEqual(len(before["skills"]["haiku-writer"]["upstream"]), 64)
        sibling.joinpath("SKILL.md").write_text(sibling.joinpath("SKILL.md").read_text() + "More.\n")
        (upstream / "SKILL.md").write_text("# The source, changed\n")
        self.commit()
        after = self.plan()
        self.assertNotEqual(before["skills"]["limerick-writer"], after["skills"]["limerick-writer"])
        self.assertNotEqual(before["skills"]["haiku-writer"]["upstream"], after["skills"]["haiku-writer"]["upstream"])

    def test_a_changed_input_changes_its_hash(self):
        before = self.plan()
        (self.world / "README.md").write_text("# Notes app, changed\n")
        self.skill_dir.joinpath("SKILL.md").write_text(self.skill_dir.joinpath("SKILL.md").read_text() + "More.\n")
        self.commit()
        after = self.plan()
        self.assertNotEqual(before["cases"], after["cases"])
        self.assertNotEqual(before["skills"], after["skills"])
        self.assertNotEqual(before["commit"], after["commit"])

    def test_an_executable_bit_is_an_input(self):
        before = self.plan()["skills"]["haiku-writer"]["sha256"]
        self.skill_dir.joinpath("SKILL.md").chmod(0o755)
        self.commit()
        self.assertNotEqual(before, self.plan()["skills"]["haiku-writer"]["sha256"])

    def test_only_the_cases_the_plan_names_are_read(self):
        draft = self.world.parent.parent / "draft"
        (draft / "world").mkdir(parents=True)
        (draft / "case.json").write_text("not json")
        self.commit()
        self.assertEqual(list(self.plan()["cases"]["haiku-writer"]), ["c1"])

    def test_a_tree_with_a_changed_or_untracked_file_is_refused(self):
        (self.world / "README.md").write_text("# Notes app, not committed\n")
        with self.assertRaisesRegex(rounds.RoundError, "clean tree.*README.md"):
            self.plan()
        self.commit()
        (self.world / "notes.md").write_text("untracked\n")
        with self.assertRaisesRegex(rounds.RoundError, "clean tree.*notes.md"):
            self.plan()

    def test_a_case_skill_or_adapter_that_does_not_exist_is_refused(self):
        for why, data in {"case": {**PLAN, "skills": {"haiku-writer": ["c1", "c9"]}},
                          "skill": {**PLAN, "skills": {"no-such-skill": ["c1"]}},
                          "adapter": {**PLAN, "hosts": [{"adapter": "no-such-host", "model": "m"}]}}.items():
            with self.subTest(why), self.assertRaises(rounds.RoundError):
                self.plan(data)

    def test_a_host_whose_program_is_not_found_is_refused(self):
        def missing(module, **containment):
            raise rounds.RoundError(f"{module.NAME}: its program {module.CLI} is not found in its jail")
        path = self.tmp / "plan.json"
        path.write_text(json.dumps(PLAN))
        with self.assertRaisesRegex(rounds.RoundError, "not found"):
            rounds.plan(path, repo=self.repo, adapters=self.adapters, version=missing)

    def test_a_manifest_is_written_once_outside_the_working_tree(self):
        record = self.plan()
        store = self.tmp / "store"
        target = rounds.write(record, store, repo=self.repo)
        self.assertEqual(json.loads(target.read_text()), record)
        self.assertEqual(rounds.write(record, store, repo=self.repo), target)  # the same plan again is kept
        with self.assertRaisesRegex(rounds.RoundError, "another manifest"):
            rounds.write({**record, "runs": 5}, store, repo=self.repo)
        with self.assertRaisesRegex(rounds.RoundError, "outside the working tree"):
            rounds.write(record, self.repo / "store", repo=self.repo)
        self.assertEqual(sorted(p.name for p in (store / "r1").iterdir()), ["manifest.json"])

    def test_a_round_folder_linked_into_the_working_tree_is_refused(self):
        store = self.tmp / "store"
        store.mkdir()
        (store / "r1").symlink_to(self.repo)
        with self.assertRaisesRegex(rounds.RoundError, "outside the working tree"):
            rounds.write(self.plan(), store, repo=self.repo)
        self.assertFalse((self.repo / "manifest.json").exists())

    def test_a_link_at_the_manifest_is_refused(self):
        store = self.tmp / "store"
        (store / "r1").mkdir(parents=True)
        elsewhere = self.tmp / "elsewhere.json"
        elsewhere.write_text("{}")
        (store / "r1" / "manifest.json").symlink_to(elsewhere)
        with self.assertRaisesRegex(rounds.RoundError, "another manifest"):
            rounds.write(self.plan(), store, repo=self.repo)
        self.assertEqual(elsewhere.read_text(), "{}")


class RealRepository(TempCase):
    def test_a_plan_of_the_real_cases_and_adapters_is_read(self):
        path = self.tmp / "plan.json"
        path.write_text(json.dumps({"round": "real", "skills": {"claims-writer": ["story-met"]},
                                    "hosts": [{"adapter": "claude-code", "model": "m1"},
                                              {"adapter": "codex", "model": "m2"}], "runs": 3}))
        record = rounds.plan(path, version=stub, at=lambda repo: "0" * 40)  # this tree may hold work in progress
        self.assertEqual(sorted(record["adapters"]), ["claude-code", "codex"])
        self.assertTrue(record["skills"]["claims-writer"]["source"].startswith("obra/superpowers@"))


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Versions(TempCase):
    def test_the_host_version_is_what_its_own_jail_finds(self):
        upstream = Upstream()
        self.addCleanup(upstream.close)
        tool = self.tmp / "tool"
        shutil.copytree(FAKE, tool, ignore=shutil.ignore_patterns("adapter.py", "__pycache__"))
        module = rounds.adapter("fakehost", FAKE.parent)
        found = rounds.host_version(module, operator_env={"PATH": f"{tool}:/usr/bin:/bin",
                                                          "HTTPS_PROXY": upstream.url},
                                    operator_home=self.tmp / "operator", host_paths=[tool])
        self.assertEqual(sorted(found), ["path", "sha256", "version"])
        self.assertEqual(found["path"], str(tool / "fakehost"))


if __name__ == "__main__":
    unittest.main()
