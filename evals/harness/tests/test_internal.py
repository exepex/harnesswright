"""The internal world reader (internal.py): a pinned commit, the one rule that leaves the skill out, the rebuilt
release and its checks, and a case's own files on top."""

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from helpers import TempCase

import internal
import lint
import manifest
import world
from cases import REPO, CaseError

SKILL = "skill-designer"  # internal in evals/kinds.json
COPIED = ["AGENTS.md", "v2/VERSION", "v2/roles.md", "v2/rules", "v2/skills"] + [
    f"v2/build/{p.name}" for p in sorted((REPO / "v2" / "build").glob("*.py"))]
NOTES = ("# Notes\n\nThe skill designer keeps its cases apart. SkillDesigner, as one word, too.\n"
         "See `release/skill-designer/SKILL.md` for the skill.\nThe end.\n")


class Adapter:
    @staticmethod
    def skill_dir(root, name):
        return root / ".host" / "skills" / name


class Reader(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "repo"
        for rel in COPIED:  # harnesswright's own sources, so the world's build and checks are the real ones
            source, target = REPO / rel, self.repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(source, target)
        self.write("notes.md", NOTES)
        self.write("evals/kinds.json", "{}\n")
        self.commit = self.git_commit("Start")
        self.paths = ["AGENTS.md", "notes.md", "evals", "v2"]

    def write(self, rel, text):
        (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / rel).write_text(text)

    def git_commit(self, message):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(world.GIT_ENV)
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", message]):
            subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=self.repo, env=env, check=True,
                           capture_output=True)
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo, env=env, check=True, capture_output=True,
                              text=True).stdout.strip()

    def kit(self, commit=None, paths=None):
        path = self.tmp / f"kit-{len(list(self.tmp.iterdir()))}.json"
        path.write_text(json.dumps({"commit": commit or self.commit, "paths": paths or self.paths,
                                    "stand_in": "toolkit author"}))
        return path

    def base(self, kit=None, name="world"):
        return internal.base(SKILL, self.tmp / name, self.repo, kit or self.kit())

    def test_the_pinned_commit_is_read_never_the_working_tree(self):
        self.write("notes.md", "Changed after the pin.\n")
        self.write("untracked.md", "Never committed.\n")
        built = self.base()
        self.assertNotIn("Changed after the pin", (built / "notes.md").read_text())
        self.assertFalse((built / "untracked.md").exists())

    def test_the_skill_under_test_and_evals_are_left_out(self):
        built = self.base()
        self.assertFalse((built / "evals").exists())
        self.assertFalse((built / "v2" / "skills" / SKILL).exists())
        self.assertFalse((built / "release" / SKILL).exists())
        self.assertTrue((built / "v2" / "skills" / "claims-writer").is_dir())
        self.assertNotIn(SKILL, (built / "AGENTS.md").read_text())
        self.assertNotIn(SKILL, (built / "v2" / "roles.md").read_text())

    def test_a_file_naming_the_skill_is_handled_by_the_one_rule(self):
        built = self.base()
        notes = (built / "notes.md").read_text()
        # A line naming the skill's folder name points at the skill and goes; its words elsewhere are renamed.
        self.assertEqual(notes, "# Notes\n\nThe toolkit author keeps its cases apart. ToolkitAuthor, as one word, "
                                "too.\nThe end.\n")
        roles = (built / "v2" / "roles.md").read_text()
        self.assertIn("| toolkit author | harness |", roles)
        for path, entry in manifest.manifest(built).items():
            if manifest.kind(entry) == "file":
                text = (built / path).read_bytes().decode("utf-8")
                self.assertFalse(lint.names(lint.Place(path, f"{path}\n{text}", "world"), SKILL), path)

    def test_the_rebuilt_release_passes_the_checks(self):
        built = self.base()
        data = json.loads((built / "release" / "manifest.json").read_text())
        self.assertEqual(sorted(data["skills"]), ["claims-writer"])
        for script in internal.BUILD[1:]:
            run = subprocess.run([os.sys.executable, "-B", script], cwd=built, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_a_world_that_fails_the_checks_is_refused(self):
        self.write("v2/VERSION", "not a version\n")
        broken = self.git_commit("Break the version")
        with self.assertRaisesRegex(CaseError, "build.py failed"):
            self.base(self.kit(broken))

    def test_a_kit_with_no_pinned_commit_builds_no_world(self):
        path = self.tmp / "unpinned.json"
        path.write_text(json.dumps({"commit": None, "paths": self.paths, "stand_in": "toolkit author"}))
        with self.assertRaisesRegex(CaseError, "no commit is pinned"):
            internal.base(SKILL, self.tmp / "none", self.repo, path)

    def internal_case(self, remove, skill=SKILL):
        return self.case({"incoming/source.md": "A borrowed source.\n"}, {"internal_world": {"remove": remove}},
                         skill=skill)

    def test_a_case_overlay_applies_on_the_built_world(self):
        case = self.internal_case(["notes.md"])
        skills = self.skill().parent
        with mock.patch.object(internal, "REPO", self.repo), mock.patch.object(internal, "KIT_FILE", self.kit()):
            base = world.build(case, Adapter, self.tmp / "arm", skills)
        self.assertEqual((base.path / "incoming" / "source.md").read_text(), "A borrowed source.\n")
        self.assertFalse((base.path / "notes.md").exists())
        self.assertTrue((base.path / "release" / "manifest.json").is_file())
        world.prove(case, Adapter, base, None, skills)

    def test_a_remove_outside_the_allow_list_is_refused(self):
        case = self.internal_case(["README.md"])
        with self.assertRaisesRegex(CaseError, "not an allow-listed path"):
            internal.world_of(case, self.tmp / "out", self.repo, self.kit())

    def test_a_team_skill_case_never_builds_on_the_internal_world(self):
        case = self.internal_case([], skill="claims-writer")
        with self.assertRaisesRegex(CaseError, "only for a case of an internal skill"):
            world.build(case, Adapter, self.tmp / "team", self.skill().parent)


if __name__ == "__main__":
    unittest.main()
