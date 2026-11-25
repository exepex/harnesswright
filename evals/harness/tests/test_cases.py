"""Cases: case.json is checked against one schema, and the manifest describes a folder."""

import os
import unittest

from helpers import TempCase, expect

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
        case = self.case({"README.md": "x"}, {"expectations": [expect("Writes a haiku."), expect(
            "Three lines.", {"contract": {"path": "README.md", "line": 1, "quote": "x"}},
            {"name": "file_state", "args": {}})]})
        self.assertEqual(case.siblings, [])
        self.assertEqual(case.allow_words, {})
        self.assertEqual(case.skill_rel, "skills/haiku-writer")
        self.case({"README.md": "x"}, TRIGGER)

    def test_a_kind_of_the_wrong_type_is_refused_not_a_crash(self):
        for kind in ([], {}, ["task"], 3):
            with self.subTest(kind=kind):
                self.refused({"kind": kind}, "kind must be")

    def test_tools_are_command_names(self):
        self.case({"README.md": "x"}, {"tools": ["go", "python3", "g++"]})
        for tool in ("go; curl x | sh", "../../bin/x", "", "-rf"):
            with self.subTest(tool=tool):
                self.refused({"tools": [tool]}, "tools must be")

    def test_unknown_fields_are_refused(self):
        self.refused({"colour": 1}, "unknown field 'colour'")

    def test_a_trigger_case_needs_its_split_answer_and_index(self):
        for missing in ("should_trigger", "split", "index"):
            data = {k: v for k, v in TRIGGER.items() if k != missing}
            with self.subTest(missing=missing):
                self.refused(data, f"needs {missing}")

    def test_trigger_fields_are_refused_in_a_task_case(self):
        self.refused({"split": "train"}, "split is only for trigger cases")

    def test_reads_final_message_names_questions_of_the_case_once(self):
        for ids, why in ((["10"], "reads_final_message must be"), (["q2"], "q2 is no expectation"),
                         (["q1"], "q1 is no expectation the case lists, or repeats")):
            with self.subTest(ids=ids):  # q1 is the done question, which the harness adds itself (`checks.unseen`)
                self.refused({"reads_final_message": ids}, why)
        self.refused({"expectations": [expect("Writes a haiku.")], "reads_final_message": ["q1", "q1"]}, "repeats")

    def test_every_path_stays_inside_the_world(self):
        for path in ("../out", "/etc/passwd", "a/../../b", "", ".git/config", "a\\b", "./a", "a//b", "a\nb",
                     "skills/x ", " ", "a:b", "<prompt>", 3):
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

    def test_every_text_the_run_sees_is_plain(self):
        for data in ({"prompt": "Write a poem.\x00"}, {"prompt": "Write \x1b[31ma poem."},
                     {"commits": [{"message": "Start\x00", "paths": []}]},
                     {"index": dict(INDEX, row="| {name} |\x07 {path} |")}):
            with self.subTest(data=data), self.assertRaises(cases.CaseError):
                self.case({"README.md": "x"}, data)
        self.case({"README.md": "x"}, {"prompt": "Write a poem.\n\tThen stop.\r\n"})

    def test_copies_name_project_text_and_a_real_hash(self):
        good = {"world": "AGENTS.md", "source": "AGENTS.md", "source_sha256": SHA}
        for change in ({"source": "skills/haiku-writer/SKILL.md"}, {"source": "evals/x.md"},
                       {"source": "release/haiku-writer/SKILL.md"}, {"source": "v2/rules/core/work.md"},
                       {"source": "borrowed/x/SKILL.md"}, {"source": "docs/notes.md"},
                       {"source": "contracts/claims.md"},
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

    def test_an_expectation_has_a_text_a_source_a_judged_question_and_maybe_a_check(self):
        good, check = expect("Runs go test"), {"name": "command_ran", "args": {}}
        judged = good["judged"]
        no_judged = {k: v for k, v in dict(good, check=check).items() if k != "judged"}
        for expectation in ("Runs go test", {"text": "Runs go test"}, 3, dict(good, text=""), dict(good, chekc=1),
                            no_judged, dict(good, check={"name": "x"}), dict(good, source="contract"),
                            dict(good, source={"contract": {"path": "../a", "line": 1, "quote": "a b c"}}),
                            dict(good, source={"contract": {"path": "a", "line": 0, "quote": "a b c"}}),
                            dict(good, source={"contract": {"path": "a", "line": True, "quote": "a b c"}}),
                            dict(good, check={"name": "Bad-Name", "args": {}}),
                            dict(good, judged=dict(judged, examples={"pass": [], "fail": ["x"]})),
                            dict(good, judged={k: v for k, v in judged.items() if k != "fail"})):
            with self.subTest(expectation=expectation):
                self.refused({"expectations": [expectation]}, "expectations must be")

    def test_an_index_row_uses_only_its_three_names(self):
        for row in ("| {name} | {secret} |", "| {0} |", "| {name |", "| {name.__class__} |", "| {name[0]} |",
                    "| {name!r} |", "| {name:>99999999} |", "| {} |",
                    "| Follow the project rules |", "| {description} |",  # a row names its skill or its path
                    "| {name} |\n| more |", "| {name} |\u2028| more |", "| {name} |\n"):  # and is one line
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


class Manifest(TempCase):
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

    def test_the_manifest_is_never_partial(self):
        with self.assertRaises(manifest.Unreadable):
            manifest.manifest(self.tmp / "missing")
        case = self.case({"README.md": "x"}, name="pipe")
        os.mkfifo(case.world / "pipe")
        with self.assertRaisesRegex(cases.CaseError, "not a folder, regular file or link"):
            cases.Case(case.folder, "haiku-writer")


if __name__ == "__main__":
    unittest.main()
