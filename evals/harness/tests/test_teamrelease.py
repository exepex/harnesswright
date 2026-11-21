"""A team skill's arms take the skill, and the run-time files where the profile names a release folder, from the
release, byte for byte (teamrelease.py, world.plan)."""

import contextlib
import hashlib
import json
import shutil
import unittest

from helpers import TempCase

import evidence
import manifest
import teamrelease
import view
import world
from cases import CaseError
from test_world import Adapter

PROFILE = "harnesswright:  # the release\n  folder: 'skills/'  # unpacked here\n  version: \"0.8.0\"\n"
RUN_TIME = ["skills/manifest.json", "skills/roles.md", "skills/rules/core/work.md"]


class TeamArms(TempCase):
    def arms(self, files, data=None, skill_dir=None):
        skills = self.release_skill().parent
        case = self.case({"README.md": "Notes app.\n", **files}, data, skill="claims-writer")
        arms = [world.build(case, Adapter, self.tmp / f"arm-{n}", skills, n, skill_dir) for n in (False, True)]
        world.prove(case, Adapter, arms[0], arms[1], skills, skill_dir)
        return case, skills, [manifest.manifest(arm.path) for arm in arms]

    def test_the_profile_folder_is_read_in_one_shape(self):
        for text, want in ((PROFILE, "skills"), ("harnesswright:\n  folder: tools/hw\n", "tools/hw"),
                           ("other:\n  folder: skills\n", None)):
            (self.tmp / "w" / ".harness").mkdir(parents=True, exist_ok=True)
            (self.tmp / "w" / teamrelease.PROFILE).write_text(text)
            self.assertEqual(teamrelease.release_folder(self.tmp / "w"), want, text)
        for text in ("harnesswright: {folder: skills}\n", "harnesswright:\n  version: 0.8.0\n"):
            (self.tmp / "w" / teamrelease.PROFILE).write_text(text)
            with self.assertRaisesRegex(CaseError, "not a block with a `folder:` line"):
                teamrelease.release_folder(self.tmp / "w")
        (self.tmp / "w" / teamrelease.PROFILE).write_text("harnesswright:\n  folder: ../out\n")
        with self.assertRaisesRegex(CaseError, "not a path inside the world"):
            teamrelease.release_folder(self.tmp / "w")

    def test_with_a_profile_the_skill_arm_holds_the_run_time_files_and_the_plain_arm_none(self):
        _, skills, (without, with_skill) = self.arms({".harness/profile.yaml": PROFILE})
        for path in RUN_TIME + ["skills/claims-writer/SKILL.md"]:
            self.assertIn(path, with_skill)
            self.assertNotIn(path, without)
        self.assertEqual((self.tmp / "arm-True" / "skills" / "manifest.json").read_bytes(),
                         (skills / "manifest.json").read_bytes())

    def test_without_a_profile_only_the_skill_folder_is_installed(self):
        _, _, (without, with_skill) = self.arms({})
        self.assertIn("skills/claims-writer/SKILL.md", with_skill)
        self.assertFalse([p for p in RUN_TIME if p in with_skill])
        others = [p for p in with_skill if p.startswith("skills/") and not p.startswith("skills/claims-writer")]
        self.assertEqual(others, [])

    def test_bytes_the_manifest_does_not_hash_are_a_harness_fault(self):
        for rel, named in (("claims-writer/SKILL.md", "SKILL.md"), ("rules/core/work.md", "rules/core/work.md")):
            with self.subTest(rel=rel):
                shutil.rmtree(self.tmp / "skills", ignore_errors=True)
                shutil.rmtree(self.tmp / "cases", ignore_errors=True)
                skills = self.release_skill().parent
                (skills / rel).write_text((skills / rel).read_text() + "Changed after the build.\n")
                self.track(skills)
                case = self.case({".harness/profile.yaml": PROFILE}, skill="claims-writer")
                with self.assertRaisesRegex(CaseError, rf"harness fault: .*different \['{named}'\]"):
                    world.plan(case, Adapter, True, skills)

    def test_a_release_with_no_hashes_is_a_harness_fault(self):
        skills = self.release_skill().parent
        data = json.loads((skills / "manifest.json").read_text())
        del data["run-time-files"]
        (skills / "manifest.json").write_text(json.dumps(data))
        case = self.case({}, skill="claims-writer")
        with self.assertRaisesRegex(CaseError, "harness fault: .*manifest.json is 0.8.0 but has no run-time-files"):
            world.plan(case, Adapter, True, skills)

    def test_a_team_task_case_installs_no_sibling(self):
        skills = self.release_skill().parent
        self.skill("haiku-writer")
        case = self.case({}, {"siblings": ["haiku-writer"]}, skill="claims-writer")
        with self.assertRaisesRegex(CaseError, "a team skill's task case installs no sibling"):
            world.plan(case, Adapter, False, skills)

    def test_the_previous_version_comes_from_its_own_release(self):
        self.release_skill()
        previous = self.tmp / "previous"
        shutil.copytree(self.tmp / "skills", previous)
        (previous / "roles.md").write_text("# Roles, as the previous release had them\n")
        data = json.loads((previous / "manifest.json").read_text())
        data["run-time-files"]["roles.md"] = hashlib.sha256((previous / "roles.md").read_bytes()).hexdigest()
        (previous / "manifest.json").write_text(json.dumps(data))
        self.track(previous)
        case = self.case({".harness/profile.yaml": PROFILE}, skill="claims-writer")
        arm = world.build(case, Adapter, self.tmp / "prev", self.tmp / "skills", True, previous / "claims-writer")
        self.assertEqual((arm.path / "skills" / "roles.md").read_text(), "# Roles, as the previous release had them\n")

    def old_release(self):
        """A previous release built before 0.8.0: no hashes, and a rules file the current release does not ship."""
        self.release_skill()
        previous = self.tmp / "previous"
        shutil.copytree(self.tmp / "skills", previous)
        data = json.loads((previous / "manifest.json").read_text())
        for key in ("run-time", "run-time-files"):
            del data[key]
        del data["skills"]["claims-writer"]["files"]
        (previous / "manifest.json").write_text(json.dumps(dict(data, **{"rulebook-version": "0.7.1"})))
        (previous / "rules" / "core" / "old.md").write_text("# Old\n")
        self.track(previous)
        return previous

    def test_a_release_before_0_8_0_is_proved_by_its_commit_and_only_as_a_previous_version(self):
        previous = self.old_release()
        case = self.case({".harness/profile.yaml": PROFILE}, skill="claims-writer")
        arm = world.build(case, Adapter, self.tmp / "old", self.tmp / "skills", True, previous / "claims-writer")
        self.assertEqual((arm.path / "skills" / "rules" / "core" / "old.md").read_text(), "# Old\n")
        self.assertTrue((arm.path / "skills" / "manifest.json").is_file())
        with self.assertRaisesRegex(CaseError, "before releases hashed their files.*only a previous version"):
            world.plan(case, Adapter, True, previous)
        read = contextlib.contextmanager(lambda repo, name, commit, sha256: iter([(previous / name, {})]))
        self.assertEqual(teamrelease.proofs(self.tmp, self.tmp / "skills" / "claims-writer", "claims-writer",
                                            {"commit": "c" * 40, "sha256": "s"}, read),
                         {"with_skill": "hashes", "previous_version": "commit"})

    def test_a_release_from_0_8_0_without_its_run_time_list_is_a_fault(self):
        skills = self.release_skill().parent
        data = json.loads((skills / "manifest.json").read_text())
        del data["run-time"]
        (skills / "manifest.json").write_text(json.dumps(data))
        case = self.case({}, skill="claims-writer")
        with self.assertRaisesRegex(CaseError, "harness fault: .*manifest.json is 0.8.0 but has no run-time list"):
            world.plan(case, Adapter, True, skills)

    def test_both_arms_give_the_same_grader_view_with_a_profile(self):
        case, skills, _ = self.arms({".harness/profile.yaml": PROFILE})
        layer = evidence.overlay(case, Adapter, skills)
        self.assertEqual(layer["release"], RUN_TIME)
        shown = []
        for arm in (False, True):
            path = self.tmp / f"arm-{arm}"
            files = manifest.manifest(path)
            blobs = {e.split(" ")[1]: (path / p).read_bytes() for p, e in files.items() if manifest.is_file(e)}
            record = {"overlay": layer, "folders": {}, "own_files": [], "files_after": files, "diff": {},
                      "case": case.id, "mode": "task", "log": [], "final_message": "Done."}
            shown.append(view.view(record, blobs.__getitem__))
        self.assertEqual(shown[0], shown[1])
        self.assertFalse([p for p in shown[1][0]["files_after"] if p.startswith("skills")])


if __name__ == "__main__":
    unittest.main()
