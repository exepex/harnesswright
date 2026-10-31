"""Cases: case.json is checked against one schema, skill frontmatter is read, and unsound worlds are found."""

import unittest

from helpers import TempCase

import cases
import manifest

INDEX = {"file": "AGENTS.md", "after": "| Skill | Path | Use when |",
         "row": "| {name} | [{path}]({path}) | {description} |"}
TRIGGER = {"kind": "trigger", "should_trigger": True, "split": "train", "index": INDEX}
SHA = "a" * 64


class Schema(TempCase):
    def refused(self, data, reason):
        with self.assertRaisesRegex(cases.CaseError, reason):
            self.case({"README.md": "x"}, data)

    def test_a_good_case_gets_its_defaults(self):
        case = self.case({"README.md": "x"}, {"expectations": ["Writes a haiku.", {"text": "Three lines."}]})
        self.assertEqual(case.siblings, [])
        self.assertEqual(case.allow_words, {})
        self.assertEqual(case.skill_rel, "skills/haiku-writer")
        self.case({"README.md": "x"}, TRIGGER)

    def test_unknown_fields_are_refused(self):
        self.refused({"colour": 1}, "unknown field 'colour'")

    def test_a_trigger_case_needs_its_split_answer_and_index(self):
        for missing in ("should_trigger", "split", "index"):
            data = {k: v for k, v in TRIGGER.items() if k != missing}
            with self.subTest(missing=missing):
                self.refused(data, f"needs {missing}")

    def test_trigger_fields_are_refused_in_a_task_case(self):
        self.refused({"split": "train"}, "split is only for trigger cases")

    def test_every_path_stays_inside_the_world(self):
        for path in ("../out", "/etc/passwd", "a/../../b", "", ".git/config", "a\\b", "./a", "a//b"):
            with self.subTest(path=path):
                self.refused({"skill_path": path}, "skill_path must be")
                self.refused({"commits": [{"message": "Start", "paths": [path]}]}, "commits must be")
                self.refused({"copies": [{"world": path, "source": "AGENTS.md", "source_sha256": SHA}]},
                             "copies must be")

    def test_commits_need_a_message(self):
        for commit in ({"message": "", "paths": []}, {"message": 3, "paths": []}, {"paths": []},
                       {"message": "Start", "paths": "README.md"}, {"message": "Start", "paths": [], "x": 1}):
            with self.subTest(commit=commit):
                self.refused({"commits": [commit]}, "commits must be")

    def test_copies_name_project_text_and_a_real_hash(self):
        good = {"world": "AGENTS.md", "source": "AGENTS.md", "source_sha256": SHA}
        for change in ({"source": "skills/haiku-writer/SKILL.md"}, {"source": "evals/x.md"},
                       {"source_sha256": "abc"}, {"source_sha256": SHA.upper()}, {"world": 7}):
            with self.subTest(change=change):
                self.refused({"copies": [dict(good, **change)]}, "copies must be")

    def test_allow_words_are_lists_of_words_for_places_the_agent_sees(self):
        self.case({"README.md": "x"}, {"allow_words": {"README.md": ["fixture"], "<prompt>": ["eval"]},
                                       "commits": [{"message": "Start", "paths": []}]})
        self.refused({"allow_words": [1]}, "allow_words must be")
        self.refused({"allow_words": {"README.md": [1]}}, "allow_words must be")
        self.refused({"allow_words": {"README.md": "fixture"}}, "allow_words must be")
        self.refused({"allow_words": {"<commit 1>": ["eval"]}}, "allow_words key")
        self.refused({"allow_words": {"../x": ["eval"]}}, "allow_words key")

    def test_expectations_are_texts_or_have_a_text(self):
        for expectation in ("", {"check": "x"}, {"text": ""}, 3):
            with self.subTest(expectation=expectation):
                self.refused({"expectations": [expectation]}, "expectations must be")

    def test_an_index_row_uses_only_its_three_names(self):
        for row in ("| {name} | {secret} |", "| {0} |", "| {name |"):
            with self.subTest(row=row):
                self.refused({"index": dict(INDEX, row=row)}, "index must be")

    def test_siblings_are_distinct_names_not_paths_and_not_the_skill(self):
        self.refused({"siblings": ["../../payload"]}, "siblings must be")
        self.refused({"siblings": ["note-taker", "note-taker"]}, "must not repeat")
        self.refused({"siblings": ["haiku-writer"]}, "cannot also be a sibling")

    def test_case_json_must_be_utf8_json(self):
        case = self.case({"README.md": "x"}, name="bytes")
        (case.folder / "case.json").write_bytes(b'{"prompt": "\xff"}')
        with self.assertRaisesRegex(cases.CaseError, "not UTF-8 JSON"):
            cases.Case(case.folder, "haiku-writer")

    def test_the_skill_name_is_a_name(self):
        case = self.case({"README.md": "x"}, name="named")
        with self.assertRaisesRegex(cases.CaseError, "not a skill name"):
            cases.Case(case.folder, "../haiku")

    def test_the_case_hash_covers_the_world_manifest(self):
        case = self.case({"run.sh": "echo ok\n"}, name="hashed")
        (case.world / "run.sh").chmod(0o755)
        self.assertNotEqual(cases.Case(case.folder, "haiku-writer").sha256, case.sha256)


class SkillFiles(TempCase):
    def test_frontmatter(self):
        self.assertEqual(cases.frontmatter("---\nname: a\ndescription: b c\n---\nbody")["description"], "b c")
        folded = "---\nname: demo\ndescription: >\n  Writes demos.\n  Use for demos.\nlicense: MIT\n---\n# Demo\n"
        self.assertEqual(cases.frontmatter(folded), {"name": "demo", "description": "Writes demos. Use for demos.",
                                                     "license": "MIT"})
        self.assertEqual(cases.frontmatter('---\nname: "a"\ndescription: \'b: c\'\n---\n')["description"], "b: c")
        self.assertEqual(cases.frontmatter("---\nname: 'it''s'\n---\n")["name"], "it's")

    def test_the_frontmatter_name_is_a_name_and_the_expected_one(self):
        folder = self.skill()
        _, meta = cases.skill_files(folder, "haiku-writer")
        self.assertEqual(meta["name"], "haiku-writer")
        with self.assertRaisesRegex(cases.CaseError, "must be 'note-taker'"):
            cases.skill_files(folder, "note-taker")
        (folder / "SKILL.md").write_text("---\nname: ../../../escape\ndescription: x\n---\n")
        with self.assertRaisesRegex(cases.CaseError, "must be a skill name"):
            cases.skill_files(folder)


class Structure(TempCase):
    def test_git_folders_and_links_that_leave_the_world_are_found(self):
        world = self.tmp / "w"
        (world / "sub" / ".git").mkdir(parents=True)
        (world / "inside").symlink_to("sub")
        (world / "absolute").symlink_to("/etc")
        (world / "sub" / "out").symlink_to("../../elsewhere")
        found = cases.structure(world)
        self.assertEqual(len(found), 3)
        self.assertTrue(any("sub/.git" in p for p in found))
        self.assertTrue(any("absolute" in p and "absolute symlink" in p for p in found))
        self.assertTrue(any("sub/out" in p and "outside" in p for p in found))

    def test_the_manifest_records_folders_modes_and_links(self):
        folder = self.tmp / "t"
        (folder / "empty").mkdir(parents=True)
        (folder / "run.sh").write_text("echo ok\n")
        (folder / "link").symlink_to("run.sh")
        found = manifest.manifest(folder)
        self.assertEqual(found["empty"], "dir")
        self.assertEqual(found["link"], "link run.sh")
        self.assertFalse(found["run.sh"].endswith(" x"))
        (folder / "run.sh").chmod(0o755)
        self.assertTrue(manifest.manifest(folder)["run.sh"].endswith(" x"))
        self.assertNotIn("empty", manifest.manifest(folder, skip=("empty",)))


if __name__ == "__main__":
    unittest.main()
