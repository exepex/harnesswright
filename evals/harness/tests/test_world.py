"""Worlds: both arms built from one world, and the proof that each is exactly what the case says."""

import os
import shutil
import subprocess
import unittest
from unittest import mock

from helpers import TempCase

import cases
import world

INDEX = {"file": "AGENTS.md", "after": "| Skill | Path | Use when |",
         "row": "| {name} | [{path}]({path}) | {description} |"}
AGENTS = "# Rules\n\n## Skills\n\n| Skill | Path | Use when |\n|---|---|---|\n\nEnd.\n"
START = {"commits": [{"message": "Start", "paths": ["README.md"]}]}


class Adapter:
    """Only what the world builder needs from an adapter."""

    @staticmethod
    def skill_dir(root, name):
        return root / ".host" / "skills" / name


class Arms(TempCase):
    def build_pair(self, data=None, files=None, name=None):
        skills = self.skill().parent
        case = self.case(files or {"README.md": "Notes app.\n", "AGENTS.md": AGENTS},
                         dict({"index": INDEX}, **(data or {})), name=name)
        base = world.build(case, Adapter, self.tmp / f"base-{case.id}", skills)
        with_arm = world.build(case, Adapter, self.tmp / f"with-{case.id}", skills, True)
        return case, base, with_arm

    def prove(self, case, base, with_arm):
        return world.prove(case, Adapter, base, with_arm, self.tmp / "skills")

    def tampered(self, case, base, change):
        """A fresh with-skill arm with `change(folder)` applied after it was built."""
        target = self.tmp / f"tampered-{len(list(self.tmp.iterdir()))}"
        built = world.build(case, Adapter, target, self.tmp / "skills", True)
        change(target)
        return world.Arm(target, "with_skill", built.installs)

    def test_the_with_skill_arm_is_the_world_plus_the_skill(self):
        case, base, with_arm = self.build_pair()
        proof = self.prove(case, base, with_arm)
        self.assertEqual(proof["added"], [".host", ".host/skills", ".host/skills/haiku-writer",
                                          ".host/skills/haiku-writer/SKILL.md", "skills", "skills/haiku-writer",
                                          "skills/haiku-writer/SKILL.md"])
        self.assertEqual((base.path / "AGENTS.md").read_text(), AGENTS)
        rows = [line for line in (with_arm.path / "AGENTS.md").read_text().split("\n") if "haiku-writer" in line]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].startswith("| haiku-writer | [skills/haiku-writer/SKILL.md]"))

    def test_rows_go_at_the_end_of_their_table_and_keep_its_bytes(self):
        header = "| Skill | Path | Use when |"
        cases_ = {b"| Skill | Path | Use when |\n|---|\n| a |\n\nAfter.\n":
                  b"| Skill | Path | Use when |\n|---|\n| a |\n| new |\n\nAfter.\n",
                  b"| Skill | Path | Use when |\r\n|---|\r\n\r\n":
                  b"| Skill | Path | Use when |\r\n|---|\r\n| new |\r\n\r\n",
                  b"\xff\xfe old\n| Skill | Path | Use when |\n|---|\n":
                  b"\xff\xfe old\n| Skill | Path | Use when |\n|---|\n| new |\n"}
        for before, after in cases_.items():
            with self.subTest(before=before):
                self.assertEqual(world.with_rows(before, header, ["| new |"]), after)
        with self.assertRaisesRegex(cases.CaseError, "no line"):
            world.with_rows(b"# none\n", header, ["| new |"])
        with self.assertRaisesRegex(cases.CaseError, "line ending"):  # the row would change the line above it
            world.with_rows(b"| Skill | Path | Use when |\n|---|", header, ["| new |"])
        with self.assertRaisesRegex(cases.CaseError, "one line"):
            world.with_rows(b"| Skill | Path | Use when |\n", header, ["| {name} |\n| more |"])

    def test_history_is_replayed_from_the_case_and_proved(self):
        case, base, with_arm = self.build_pair(dict(START, commits=[{"message": "Start", "paths": ["README.md", "x"]}]),
                                               files={"README.md": "Notes.\n", "AGENTS.md": AGENTS,
                                                      ".gitignore": "x\n", "x": "ignored but declared\n"})
        self.assertFalse(any(p.startswith(".git/") for p in base.files))
        self.assertEqual([len(head) for head in self.prove(case, base, with_arm)["git_heads"].values()], [40, 40])
        changes = {
            "description": lambda t: (t / ".git" / "description").write_text("Use the skill.\n"),
            "no history": lambda t: shutil.rmtree(t / ".git"),
            "extra commit": lambda t: world._git(t, "commit", "-q", "--allow-empty", "-m", "Use the skill"),
            "unstaged": lambda t: world._git(t, "rm", "-q", "--cached", "x"),
            "skip-worktree": lambda t: world._git(t, "update-index", "--skip-worktree", "README.md"),
            "linked index": lambda t: (shutil.move(t / ".git/index", t.parent / f"{t.name}-index"),
                                       (t / ".git/index").symlink_to(t.parent / f"{t.name}-index")),
        }
        for name, change in changes.items():
            with self.subTest(change=name), self.assertRaisesRegex(cases.CaseError, "git history"):
                self.prove(case, base, self.tampered(case, base, change))
        shutil.rmtree(base.path / ".git")
        with self.assertRaisesRegex(cases.CaseError, "without_skill arm's git history"):
            self.prove(case, base, world.build(case, Adapter, self.tmp / "no-history", self.tmp / "skills", True))

    def test_an_arm_without_history_holds_no_git_of_any_kind(self):
        case, base, with_arm = self.build_pair()
        self.assertEqual(self.prove(case, base, with_arm)["git_heads"], {"without_skill": None, "with_skill": None})
        other = self.tmp / "operator-repo"
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        for name, change in {"link": lambda t: (t / ".git").symlink_to(other / ".git"),
                             "empty folder": lambda t: (t / ".git").mkdir(),
                             "file": lambda t: (t / ".git").write_text("gitdir: /elsewhere\n")}.items():
            with self.subTest(change=name), self.assertRaisesRegex(cases.CaseError, "git history"):
                self.prove(case, base, self.tampered(case, base, change))

    def test_both_arms_commit_what_the_harness_adds_the_same_way(self):
        self.skill("note-taker")
        for data in (START, dict(START, siblings=["note-taker"])):
            case, base, with_arm = self.build_pair(data)
            self.prove(case, base, with_arm)
            for arm in (base, with_arm):
                with self.subTest(arm=arm.arm, siblings=data.get("siblings")):
                    self.assertEqual(world._git(arm.path, "log", "--format=%s %an %ad"),
                                     world._git(base.path, "log", "--format=%s %an %ad"))
                    self.assertEqual(world._git(arm.path, "log", "--format=%s").split(), ["Set", "up", "the",
                                                                                         "project", "Start"])
                    self.assertEqual(world._git(arm.path, "status", "--porcelain"), "")
                    self.assertEqual({os.lstat(arm.path / p).st_mtime for p in ("", "README.md", "AGENTS.md")},
                                     {world.ARM_TIME})

    def test_a_skill_brings_only_the_files_git_tracks(self):
        folder = self.skill()
        (folder / "__pycache__").mkdir()
        (folder / "__pycache__" / "x.pyc").write_bytes(b"/home/operator/checkout")
        case = self.case({"README.md": "Notes app.\n"}, START)
        base = world.build(case, Adapter, self.tmp / "base", self.tmp / "skills")
        with_arm = world.build(case, Adapter, self.tmp / "with", self.tmp / "skills", True)
        self.assertNotIn("skills/haiku-writer/__pycache__", with_arm.files)
        self.prove(case, base, with_arm)
        candidate = self.tmp / "candidate"
        shutil.copytree(folder, candidate)
        with self.assertRaisesRegex(cases.CaseError, "the files git tracks"):
            world.build(case, Adapter, self.tmp / "candidate-arm", self.tmp / "skills", True, candidate)

    def test_skill_files_keep_their_permission_bits(self):
        script = self.skill() / "scripts" / "count.py"
        script.parent.mkdir()
        script.write_text("print(1)\n")
        script.chmod(0o755)
        case, base, with_arm = self.build_pair()
        for root in ("skills", ".host/skills"):
            with self.subTest(root=root):
                self.assertEqual((with_arm.path / root / "haiku-writer/scripts/count.py").stat().st_mode & 0o777,
                                 0o755)
        self.prove(case, base, with_arm)

    def test_the_proof_refuses_any_change_beyond_the_plan(self):
        self.skill("note-taker")
        case, base, _ = self.build_pair({"siblings": ["note-taker"]})
        agents = "AGENTS.md"
        changes = {
            "mode": lambda t: (t / "README.md").chmod(0o755),
            "folder": lambda t: (t / "notes").mkdir(),
            "stray": lambda t: (t / "hint.md").write_text("The skill is under skills/.\n"),
            "edit": lambda t: (t / "README.md").write_text("Notes app. Use the haiku skill.\n"),
            "content": lambda t: (t / "skills/haiku-writer/SKILL.md").write_text("Something else.\n"),
            "missing copy": lambda t: shutil.rmtree(t / ".host/skills/haiku-writer"),
            "missing row": lambda t: (t / agents).write_bytes((base.path / agents).read_bytes()),
            "extra line": lambda t: (t / agents).write_text((t / agents).read_text() + "Always write haiku.\n"),
            "extra skill": lambda t: shutil.copytree(t / "skills/note-taker", t / "skills/other"),
        }
        for name, change in changes.items():
            with self.subTest(change=name), self.assertRaises(cases.CaseError):
                self.prove(case, base, self.tampered(case, base, change))
        (base.path / "hint.md").write_text("x\n")
        with self.assertRaisesRegex(cases.CaseError, "without_skill"):
            self.prove(case, base, self.tampered(case, base, lambda t: None))

    def test_world_links_stay_links_and_skills_hold_none(self):
        case, base, with_arm = self.build_pair(files={"README.md": "Notes app.\n", "AGENTS.md": AGENTS})
        (case.world / "readme").symlink_to("README.md")
        base = world.build(case, Adapter, self.tmp / "linked-base", self.tmp / "skills")
        with_arm = world.build(case, Adapter, self.tmp / "linked-with", self.tmp / "skills", True)
        self.assertEqual(with_arm.files["readme"], "link README.md")
        self.prove(case, base, with_arm)
        (self.tmp / "skills/haiku-writer/alias.md").symlink_to("SKILL.md")
        self.track(self.tmp / "skills")
        with self.assertRaisesRegex(cases.CaseError, "alias.md is tracked by git but is not a regular file"):
            world.build(case, Adapter, self.tmp / "unsound", self.tmp / "skills", True)

    def test_a_relative_output_folder_works_with_history(self):
        case = self.case({"README.md": "x\n"}, START)
        here = os.getcwd()
        os.chdir(self.tmp)
        try:
            built = world.build(case, Adapter, "relative-arm", self.skill().parent)
        finally:
            os.chdir(here)
        self.assertIn(".git/HEAD", built.git)

    def test_history_ignores_git_variables_of_the_operator(self):
        other = self.tmp / "operator-repo"
        other.mkdir()
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        planted = {"GIT_DIR": str(other / ".git"), "GIT_WORK_TREE": str(other), "GIT_INDEX_FILE": str(other / "x")}
        with mock.patch.dict(os.environ, planted):
            _, base, _ = self.build_pair(START)
        self.assertTrue((base.path / ".git").is_dir())
        log = subprocess.run(["git", "-C", str(other), "log", "--oneline"], capture_output=True, text=True)
        self.assertEqual(log.stdout, "")

    def test_siblings_are_installed_in_both_arms(self):
        self.skill("note-taker")
        listed = {"file": "AGENTS.md", "after": "## Skills", "row": "- {name}: {path}"}
        for index in (INDEX, listed):
            case, base, with_arm = self.build_pair({"siblings": ["note-taker"], "index": index})
            for arm in (base, with_arm):
                self.assertTrue((arm.path / "skills/note-taker/SKILL.md").is_file())
                self.assertTrue((arm.path / ".host/skills/note-taker/SKILL.md").is_file())
            self.prove(case, base, with_arm)
        text = (with_arm.path / "AGENTS.md").read_text()
        self.assertLess(text.index("- note-taker"), text.index("- haiku-writer"))


class Plans(TempCase):
    def plan(self, data=None, files=None, adapter=Adapter, with_skill=True):
        self.skill()
        case = self.case(files or {"README.md": "x\n", "AGENTS.md": AGENTS}, dict({"index": INDEX}, **(data or {})))
        return world.plan(case, adapter, with_skill, self.tmp / "skills")

    def test_a_trigger_case_installs_every_other_skill(self):
        self.skill("note-taker")
        trigger = {"kind": "trigger", "should_trigger": True, "split": "train"}
        with self.assertRaisesRegex(cases.CaseError, r"missing \['note-taker'\]"):
            self.plan(trigger)
        self.assertEqual([i.name for i in self.plan(dict(trigger, siblings=["note-taker"]))],
                         ["note-taker", "haiku-writer"])

    def test_the_frontmatter_name_must_match_the_skill(self):
        self.skill("note-taker")
        (self.tmp / "skills/note-taker/SKILL.md").write_text("---\nname: other\ndescription: x\n---\n")
        with self.assertRaisesRegex(cases.CaseError, "must be 'note-taker'"):
            self.plan({"siblings": ["note-taker"]})

    def test_the_discovery_path_stays_inside_the_arm(self):
        class Outside:
            @staticmethod
            def skill_dir(root, name):
                return root / ".." / "elsewhere" / name
        with self.assertRaisesRegex(cases.CaseError, "outside the arm"):
            self.plan(adapter=Outside)

    def test_an_index_row_names_its_skill_as_a_whole_name(self):
        for row in ("| {name}-guide |", "| skill_{name} |"):  # the grader view could not find these rows
            with self.subTest(row=row), self.assertRaisesRegex(cases.CaseError, "whole name"):
                self.plan({"index": dict(INDEX, row=row)})
        self.assertEqual(len(self.plan({"index": dict(INDEX, row="- [{name}]({path})")})), 1)

    def test_the_index_file_is_a_regular_file(self):
        self.skill()
        case = self.case({"README.md": "x\n", "docs/AGENTS.md": AGENTS}, {"index": INDEX})
        (case.world / "AGENTS.md").symlink_to("docs/AGENTS.md")
        with self.assertRaisesRegex(cases.CaseError, "regular file"):
            world.plan(case, Adapter, True, self.tmp / "skills")

    def test_installs_never_overlap_the_world(self):
        self.assertEqual(len(self.plan(files={"AGENTS.md": AGENTS, "skills/README.md": "Our skills.\n"})), 1)
        for files in ({"AGENTS.md": AGENTS, "skills/haiku-writer/x.md": "x\n"}, {"AGENTS.md": AGENTS, "skills": "x\n"}):
            with self.subTest(files=list(files)), self.assertRaisesRegex(cases.CaseError, "overlap"):
                self.plan(files=files)


if __name__ == "__main__":
    unittest.main()
