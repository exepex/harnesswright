"""The internal world reader (internal.py): a pinned commit, the one rule that leaves the skill out, the rebuilt
release and its checks, and a case's own files on top."""

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from helpers import TempCase, expect

import internal
import lint
import manifest
import world
from cases import REPO, CaseError, load_cases

SKILL = "skill-designer"  # internal in evals/kinds.json
# A task case of a skill with a kind needs a contract expectation (cited.py); this one cites incoming/notes.md.
NOTE = {"contract": {"path": "incoming/notes.md", "line": 1, "quote": "Ship the release on Friday."}}
SCORED = {"internal_world": {"remove": []}, "expectations": [
    expect("The release ships on Friday", NOTE, {"name": "own_release_checks", "args": {}})]}
COPIED = ["AGENTS.md", "docs/design", "v2/VERSION", "v2/roles.md", "v2/rules", "v2/skills"] + [
    f"v2/build/{p.name}" for p in sorted((REPO / "v2" / "build").glob("*.py"))]
NOTES = ("# Notes\n\nThe skill designer keeps its cases apart. SkillDesigner, as one word, too.\n"
         "See `release/skill-designer/SKILL.md` for the skill.\nThe end.\n")
NOTE_TAKER = ("---\nname: note-taker\ndescription: Write the notes of a meeting. Do not use for minutes.\nmetadata:\n"
              "  roles: implementer\n  areas: rest\n---\n\n1. Read the meeting.\n2. Write the notes.\n")


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

    def lint(self, case, kit=()):
        with mock.patch.object(internal, "REPO", self.repo), mock.patch.object(internal, "KIT_FILE", self.kit()):
            return lint.lint_case(case, Adapter, self.tmp / "arms", self.skill().parent, kit=kit), \
                internal.resolve(case).world

    def test_a_clean_case_on_the_pinned_base_has_no_problems(self):
        case = self.case({"incoming/notes.md": "Ship the release on Friday.\n"}, SCORED, skill=SKILL)
        problems, built = self.lint(case)
        self.assertTrue((built / "docs" / "design" / "11-evals.md").is_file())  # tells and arm names in the base
        self.assertEqual(problems, [])
        unscored = self.case({"incoming/notes.md": "Ship the release on Friday.\n"},
                             dict(SCORED, expectations=[expect("The release ships on Friday")]), skill=SKILL)
        shutil.rmtree(self.tmp / "arms")
        unchecked = (f"{unscored.id}: an internal task case needs a contract expectation that one of harnesswright's "
                     "own checks decides (evals/own-checks.json): with none, the round lists it unchecked and its "
                     "skill's label stays at most inconclusive (verdicts.decide)")
        self.assertEqual(self.lint(unscored)[0], [
            f"{unscored.id}: a task case needs at least one contract expectation: with none, no run of it is scored "
            "(verdicts.task_outcome), and its skill's label stays at most inconclusive", unchecked])
        judged = self.case({"incoming/notes.md": "Ship the release on Friday.\n"},
                           dict(SCORED, expectations=[expect("The release ships on Friday", NOTE)]), skill=SKILL)
        shutil.rmtree(self.tmp / "arms")
        # a contract expectation, but none that an own check decides
        self.assertEqual(self.lint(judged)[0], [unchecked.replace(unscored.id, judged.id, 1)])

    def test_the_lint_reads_the_pinned_base_as_project_text_and_the_case_own_files_by_every_rule(self):
        pinned = next(line for line in (REPO / "docs" / "design" / "11-evals.md").read_text().splitlines()
                      if len(line.split()) > 12 and not any(t in line.lower() for t in lint.TELLS))
        # `pinned` is base text that the kit's eval text repeats, so it is project text even in the case's own file
        measured = "Each run of this case is scored on the stage report it writes for the next owner."
        case = self.case({"incoming/source.md": f"A borrowed source, with its test fixture.\n{measured}\n{pinned}\n",
                          "incoming/with_skill.md": "Notes.\n", "incoming/notes.md": "Ship the release on Friday.\n"},
                         SCORED, skill=SKILL)
        problems, built = self.lint(case, [measured, pinned])
        base = [p for p in manifest.manifest(built) if (built / p).is_file() and not p.startswith("incoming/")
                and lint.told(lint.Place(p, (built / p).read_text(), "world"), "eval")
                and "with_skill" in (built / p).read_text()]
        self.assertTrue(base)  # the base holds tell words and arm names, such as docs/design/11-evals.md
        own = f"{case.id}: incoming/"
        self.assertEqual([p for p in problems if not p.startswith(own)], [])  # none from the base
        found = {p[len(own):].split(",")[0] for p in problems}
        self.assertEqual({"source.md: holds eval text", "source.md: test-tell word 'fixture'",
                          "with_skill.md: names the arm 'with_skill'"}, found)

    def test_the_skill_name_rule_reads_the_whole_built_world(self):
        case = self.case({"incoming/notes.md": "Notes.\n"}, {"internal_world": {"remove": []}}, skill=SKILL)
        with mock.patch.object(internal, "leave_out", return_value=[]):  # a base the one rule did not clean
            problems, _ = self.lint(case)
        self.assertTrue(any(p.startswith(f"{case.id}: notes.md: names the skill") for p in problems), problems)

    def test_a_removed_source_leaves_a_release_the_build_makes_and_a_removed_copy_alone_is_refused(self):
        source, copy = "v2/rules/core/index.md", "release/rules/core/index.md"
        self.write("release/README.md", "Built by v2/build/build.py.\n")  # so the kit may list release/
        kit = self.kit(self.git_commit("Add a release folder"), self.paths + ["release"])
        case = self.case({}, {"internal_world": {"remove": [source, copy]}}, skill=SKILL)
        shutil.rmtree(case.folder / "world")
        out = internal.world_of(type(case)(case.folder, SKILL), self.tmp / "out", self.repo, kit)
        self.assertFalse((out / source).exists() or (out / copy).exists())
        self.assertNotIn("rules/core/index.md", (out / "release" / "manifest.json").read_text())  # rebuilt without it
        alone = self.case({}, {"internal_world": {"remove": [copy]}}, skill=SKILL)
        shutil.rmtree(alone.folder / "world")
        with self.assertRaisesRegex(CaseError, f"remove {copy}: the build puts it back"):
            internal.world_of(type(alone)(alone.folder, SKILL), self.tmp / "alone", self.repo, kit)

    def test_an_internal_case_may_add_no_file(self):
        case = self.case({}, {"internal_world": {"remove": ["notes.md"]}}, skill=SKILL)
        shutil.rmtree(case.folder / "world")
        case = type(case)(case.folder, SKILL)
        out = internal.world_of(case, self.tmp / "out", self.repo, self.kit())
        self.assertFalse((out / "notes.md").exists())
        self.assertTrue((out / "AGENTS.md").is_file())
        plain = self.case({}, skill=SKILL)
        shutil.rmtree(plain.folder / "world")
        with self.assertRaisesRegex(CaseError, "no world/ folder"):
            type(plain)(plain.folder, SKILL)

    def test_a_skill_the_case_brings_is_built_with_its_job_row_and_refused_in_no_job(self):
        files = {"v2/skills/note-taker/SKILL.tmpl.md": NOTE_TAKER}
        row = "| notes | implementer | note-taker | note-taker |"
        case = self.case(files, {"internal_world": {"remove": [], "jobs": [row]}}, skill=SKILL)
        out = internal.world_of(case, self.tmp / "out", self.repo, self.kit())
        self.assertIn(row, (out / "v2" / "roles.md").read_text().split("\n"))
        self.assertTrue((out / "release" / "note-taker" / "SKILL.md").is_file())
        alone = self.case(files, {"internal_world": {"remove": []}}, skill=SKILL)
        refused = "the world with the case's files fails its build: .*note-taker is in no job"
        with self.assertRaisesRegex(CaseError, refused):
            internal.world_of(alone, self.tmp / "alone", self.repo, self.kit())

    def test_a_case_never_writes_what_the_pinned_build_owns_and_its_job_rows_are_its_own_text(self):
        for n, (rel, at) in enumerate((("v2/build/build.py", "v2/build"), ("release/manifest.json", "release"),
                                       ("release", "release"), ("v2", "v2"))):  # its folder found at, then above
            with self.subTest(rel), self.assertRaisesRegex(CaseError, f"world/{at}: the pinned build owns"):
                case = self.case({rel: "import sys\nsys.exit(0)\n"}, {"internal_world": {"remove": []}}, skill=SKILL)
                internal.world_of(case, self.tmp / f"out-{n}", self.repo, self.kit())
        plant = lambda folder, rows, name: (Path(folder) / "v2" / "build" / "build.py").write_text("raise SystemExit\n")
        case = self.case({"incoming/a.md": "A.\n"}, {"internal_world": {"remove": []}}, skill=SKILL)
        with mock.patch.object(internal, "add_jobs", plant), self.assertRaisesRegex(  # a name the name test misses
                CaseError, "v2/build/build.py: the case's files changed what the pinned build owns"):
            internal.world_of(case, self.tmp / "out-planted", self.repo, self.kit())
        row = "| grader | implementer | note-taker | note-taker |"
        case = self.case({"v2/skills/note-taker/SKILL.tmpl.md": NOTE_TAKER},
                         {"internal_world": {"remove": [], "jobs": [row]}}, skill=SKILL)
        problems, built = self.lint(case)
        self.assertIn(f"{case.id}: <job rows>: test-tell word 'grader'", problems)
        self.assertEqual(case.own_files["release/roles.md"], "derived")  # the build's copy is the case's too

    def test_a_base_path_the_case_changed_is_never_project_text_whatever_its_line_breaks(self):
        row = "| notes | implementer | note-taker | note-taker |"
        for mark in (" ", "\u2028", "\u2029"):  # the last two break lines for str.splitlines, not for the lint
            with self.subTest(mark=repr(mark)):
                files = {"incoming/notes.md": "Ship the release on Friday.\n",
                         "v2/skills/note-taker/SKILL.tmpl.md": NOTE_TAKER,
                         "v2/skills/note-taker/references/extra.md": f"The release ships on Friday.{mark}Done.\n"}
                case = self.case(files, dict(SCORED, internal_world={"remove": [], "jobs": [row]}), skill=SKILL)
                shutil.rmtree(self.tmp / "arms", ignore_errors=True)
                problems, _ = self.lint(case)  # the release copy of extra.md excuses nothing at its source
                self.assertIn(f"{case.id}: v2/skills/note-taker/references/extra.md: holds expectation text", problems)

    def test_a_golden_is_excused_what_its_case_wrote_and_never_the_base(self):
        row = "| notes | implementer | note-taker | note-taker |"
        case = self.case({"v2/skills/note-taker/SKILL.tmpl.md": NOTE_TAKER},
                         {"internal_world": {"remove": [], "jobs": [row]}}, skill=SKILL)
        (case.folder / "world" / "incoming").mkdir()
        link = case.folder / "world" / "incoming" / "design.md"
        link.symlink_to("../docs/design/11-evals.md")  # its text is the target string, never the file
        case = type(case)(case.folder, SKILL)
        long = lambda text: [line for line in text.splitlines() if len(lint.words(line)) >= lint.RUN]
        with mock.patch.object(internal, "REPO", self.repo), mock.patch.object(internal, "KIT_FILE", self.kit()):
            built = internal.resolve(case).world
            copy = built / "release" / "note-taker" / "SKILL.md"
            own = lint.all_runs([NOTE_TAKER, (case.folder / "case.json").read_text()], {lint.RUN})
            made = sorted(lint.all_runs([f"release/note-taker/SKILL.md\n{copy.read_text()}"], {lint.RUN})
                          - case.base_runs - own)[0]  # a run only the build made of the case's file: excused
            base = {"in a file the case left alone": long((built / "docs" / "design" / "10-skills.md").read_text())[0],
                    "in a file the case changed": long((built / "v2" / "roles.md").read_text())[0],
                    "behind a link the case wrote": long((built / "docs" / "design" / "11-evals.md").read_text())[0]}
            for where, line in base.items():
                with self.subTest(where):
                    golden = json.dumps({"log": [{"text": made}, {"text": line}]})
                    said = lint.golden_said(case.folder, golden, SKILL)
                    self.assertEqual(set(said), lint.all_runs([line], {lint.RUN}))  # the base's runs, never the case's

    def test_a_remove_comes_after_the_rebuild(self):
        case = self.internal_case(["v2/VERSION"])  # the build needs it, so it is removed only after the build
        out = internal.world_of(case, self.tmp / "out", self.repo, self.kit())
        self.assertFalse((out / "v2" / "VERSION").exists())
        self.assertTrue((out / "release" / "manifest.json").is_file())

    def test_jobs_need_a_jobs_table_and_rows_of_one_line(self):
        (self.tmp / "bare" / "v2").mkdir(parents=True)
        (self.tmp / "bare" / "v2" / "roles.md").write_text("# Roles\n")
        with self.assertRaisesRegex(CaseError, "c1: jobs: v2/roles.md has no Jobs table"):
            internal.add_jobs(self.tmp / "bare", ["| a | b | c | c |"], "c1")
        for row in ("notes | implementer", "| notes |\n| more |"):
            with self.subTest(row=row), self.assertRaisesRegex(CaseError, "internal_world must be"):
                self.case({}, {"internal_world": {"remove": [], "jobs": [row]}}, skill=SKILL)

    @unittest.skipIf(json.loads(internal.KIT_FILE.read_text())["commit"] is None,
                     "the kit pins no commit yet; the judges approve `left_out` with the pin")
    def test_a_clean_case_on_the_real_pin_has_no_problems(self):
        from test_adapters import CLAUDE
        case = self.case({"incoming/notes.md": "Ship the release on Friday.\n"}, SCORED, skill=SKILL)
        self.assertEqual(lint.lint_case(case, CLAUDE, self.tmp / "arms", None), [])

    @unittest.skipIf(json.loads(internal.KIT_FILE.read_text())["commit"] is None,
                     "the kit pins no commit yet; the judges approve `left_out` with the pin")
    def test_the_kit_left_out_list_matches_the_pin(self):
        internal.base(SKILL, self.tmp / "pinned")

    @unittest.skipIf(json.loads(internal.KIT_FILE.read_text())["commit"] is None,
                     "the kit pins no commit yet; the judges approve `left_out` with the pin")
    def test_every_commit_a_case_label_names_is_in_its_built_history(self):
        # A label in a case's world names the commit its round ran on. The replayed history depends on the pin, so
        # after a re-pin a label may name a commit no arm holds; it fails here, not quietly in a run.
        for case in load_cases(SKILL):
            labels = sorted((case.folder / "world" / "evals" / "results").glob("*.json"))
            named = {json.loads(p.read_text()).get("commit") for p in labels} - {None}
            if not (named and case.commits):
                continue
            with self.subTest(case=case.id):
                out = internal.world_of(case, self.tmp / case.id)
                world._history(out, case.commits)
                held = subprocess.run(["git", "rev-list", "--all"], cwd=out, capture_output=True, text=True,
                                      check=True).stdout.split()
                self.assertEqual(named - set(held), set())


if __name__ == "__main__":
    unittest.main()
