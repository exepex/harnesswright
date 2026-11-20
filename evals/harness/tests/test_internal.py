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
COPIED = ["AGENTS.md", "docs/design", "v2/VERSION", "v2/roles.md", "v2/rules", "v2/skills"] + [
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
        self.paths = ["AGENTS.md", "docs", "notes.md", "evals", "v2"]

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

    def kit(self, commit=None, paths=None, left_out=None):
        """A kit pinned at `commit`, approving `left_out`, or else what the rule leaves out there."""
        commit, paths = commit or self.commit, paths or self.paths
        if left_out is None:
            scratch = self.tmp / f"scratch-{len(list(self.tmp.iterdir()))}"
            internal.read_pinned(self.repo, commit, paths, scratch)
            shutil.rmtree(scratch / internal.RELEASE, ignore_errors=True)
            left_out = internal.leave_out(scratch, SKILL, "toolkit author")
        path = self.tmp / f"kit-{len(list(self.tmp.iterdir()))}.json"
        path.write_text(json.dumps({"commit": commit, "paths": paths, "stand_in": "toolkit author",
                                    "left_out": left_out}))
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
        path.write_text(json.dumps({"commit": None, "paths": self.paths, "stand_in": "toolkit author",
                                    "left_out": []}))
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

    def test_a_name_split_by_punctuation_is_never_rewritten(self):
        cases = {"the skill. Designer": "the skill. Designer", "skill, designer": "skill, designer",
                 "Skill Designers": "Toolkit authors", "skill_designer": "toolkit_author",
                 "SkillDesigner": "ToolkitAuthor", "a skill-designer.": "a toolkit-author."}
        for text, want in cases.items():
            self.assertEqual(internal._rename(text, SKILL, "toolkit author"), want, text)

    def test_the_world_refuses_a_name_the_rule_cannot_rewrite(self):
        self.write("notes.md", "The skill. Designer of it.\n")
        with self.assertRaisesRegex(CaseError, "the lint still finds skill-designer"):
            self.base(self.kit(self.git_commit("Split the name"), left_out=[]))

    def test_a_field_table_drops_its_whole_section(self):
        self.write("notes.md", "# Sources\n\n## one\n\n| Field | Value |\n|---|---|\n| Path | `x` |\n"
                               "| Used in | `v2/skills/skill-designer/` |\n\n### Changes\n\nAll of them.\n\n"
                               "## two\n\n| Field | Value |\n|---|---|\n| Path | `y` |\n")
        kit = self.kit(self.git_commit("Add a record"))
        built = self.base(kit)
        self.assertEqual((built / "notes.md").read_text(), "# Sources\n\n## two\n\n| Field | Value |\n|---|---|\n"
                                                         "| Path | `y` |\n")
        notes = [row for row in json.loads(kit.read_text())["left_out"] if row[0] == "notes.md"]
        self.assertEqual([row[1] for row in notes], list(range(3, 14)))
        self.assertTrue(all(row[3] is None for row in notes))

    def test_the_left_out_list_must_be_the_approved_one(self):
        approved = json.loads(self.kit().read_text())["left_out"]
        self.assertIn(["AGENTS.md", 94, approved[0][2], None], approved)
        self.assertIn(["notes.md", 4, "See `release/skill-designer/SKILL.md` for the skill.", None], approved)
        self.assertIn(["v2/skills/skill-designer", None, None, None], approved)
        with self.assertRaisesRegex(CaseError, "not the kit's approved `left_out` list: 2 found, 0 approved"):
            self.base(self.kit(self.commit, ["notes.md", "evals"], left_out=[]))

    def test_a_world_whose_files_name_a_missing_file_is_refused(self):
        for text in ("See [the guide](docs/guide.md#start).\n", "@docs/guide.md\n"):
            with self.subTest(text=text):
                self.write("notes.md", text)
                with self.assertRaisesRegex(CaseError, "names files it lacks: notes.md -> docs/guide.md"):
                    self.base(self.kit(self.git_commit(f"Link {len(text)}")), f"w{len(text)}")
        self.write("notes.md", "See [the guide](docs/design/README.md) and [a site](https://example.com).\n")
        self.base(self.kit(self.git_commit("Link a file the world has")), "fine")

    def test_a_case_file_naming_a_missing_file_is_refused(self):
        case = self.case({"incoming/source.md": "Read [the brief](../brief.md).\n"},
                         {"internal_world": {"remove": []}}, skill=SKILL)
        with self.assertRaisesRegex(CaseError, "incoming/source.md -> ../brief.md"):
            internal.world_of(case, self.tmp / "out", self.repo, self.kit())

    def test_the_lint_holds_only_the_case_own_files_to_the_tell_and_eval_rules(self):
        measured = next(line for line in (REPO / "docs" / "design" / "11-evals.md").read_text().splitlines()
                        if len(line.split()) > 12)  # pinned base text that is also eval text
        case = self.case({"incoming/source.md": f"A borrowed source, with its test fixture.\n{measured}\n"},
                         {"internal_world": {"remove": []}}, skill=SKILL)
        with mock.patch.object(internal, "REPO", self.repo), mock.patch.object(internal, "KIT_FILE", self.kit()):
            problems = lint.lint_case(case, Adapter, self.tmp / "arms", self.skill().parent, kit=[measured])
            built = internal.resolve(case).world
        base = [p for p in manifest.manifest(built) if (built / p).is_file()
                and lint.told(lint.Place(p, (built / p).read_text(), "world"), "eval")]
        self.assertTrue(base)  # the pinned base holds tell words, such as docs/design/11-evals.md
        own = f"{case.id}: incoming/source.md: "
        ruled = [p for p in problems if "test-tell word" in p or "holds eval text" in p]
        self.assertEqual(ruled, [p for p in problems if p.startswith(own)], problems)  # none from the base
        found = {p[len(own):].split(",")[0] for p in ruled}
        self.assertLessEqual({"holds eval text", "test-tell word 'fixture'"}, found)

    @unittest.skipIf(json.loads(internal.KIT_FILE.read_text())["commit"] is None,
                     "the kit pins no commit yet; the judges approve `left_out` with the pin")
    def test_the_kit_left_out_list_matches_the_pin(self):
        internal.base(SKILL, self.tmp / "pinned")


if __name__ == "__main__":
    unittest.main()
