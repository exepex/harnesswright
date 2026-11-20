"""Script checks: every check gives the outcome of each of its answer keys, has one that must pass and one that must
fail, decides a stored bundle as it decides its key, never decides on inferred evidence, leaves an own check that
runs too long undecided, and stops the round when it is broken or given arguments outside its list."""

import hashlib
import json
import sys
from unittest import mock

from helpers import TempCase

import checks
import evidence


class Library(TempCase):
    def test_every_check_gives_the_outcome_of_each_answer_key(self):
        library = checks.library()
        self.assertEqual(sorted(library), ["blocked_after_failed_check", "changes_only_in", "cites_listed_ids",
                                         "command_ran", "ended_blocked", "ends_with_one_question", "field_words",
                                         "file_state", "frontmatter", "line_counts", "line_references",
                                         "lists_every_change", "no_shared_words", "own_case_files",
                                         "own_release_checks", "rule_tags", "sections", "shares_words"])
        for name in library:
            with self.subTest(check=name):
                self.assertEqual(checks.prove(name, library), {})

    def test_loading_the_library_leaves_no_bytecode_in_it(self):
        with mock.patch.object(sys, "dont_write_bytecode", False):  # as an operator's python runs it
            checks.library()
        self.assertEqual(sorted(checks.LIBRARY.rglob("__pycache__")), [])

    def test_every_answer_key_folder_names_a_check(self):
        self.assertEqual(sorted(p.name for p in checks.KEYS.iterdir()), sorted(checks.library()))

    def test_a_check_without_a_key_that_must_fail_is_refused(self):
        folder = self.tmp / "keys" / "file_state"
        folder.mkdir(parents=True)
        (folder / "one.json").write_text(json.dumps({"args": {"path": "a", "state": "absent"}, "outcome": "pass"}))
        with self.assertRaisesRegex(checks.CheckError, "one that must fail"):
            checks.prove("file_state", folder=self.tmp / "keys")
        (folder / "two.json").write_text(json.dumps({"args": {}, "outcome": "maybe"}))
        with self.assertRaisesRegex(checks.CheckError, "an answer key holds"):
            checks.keys("file_state", self.tmp / "keys")

    def test_a_stored_bundle_is_decided_as_its_key(self):
        key = checks.keys("file_state")["changed-pass"]
        made = checks.Bundle.key(key)
        blobs = {}
        for text in key["after"].values():
            blobs[hashlib.sha256(text.encode()).hexdigest()] = text.encode()
        transcript = hashlib.sha256(b"").hexdigest()
        blobs[transcript] = b""
        record = {"files_after": made.files, "diff": made.changes, "log": [], "final_message": None,
                  "transcript": {"stdout": transcript, "stderr": transcript}}
        stored = checks.Bundle.load(evidence.store(record, blobs, self.tmp / "bundle"))
        self.assertEqual(checks.decide("file_state", stored, key["args"])["outcome"], "pass")
        self.assertEqual(stored.text("src/app.py"), key["after"]["src/app.py"])

    def test_a_check_never_decides_on_inferred_evidence(self):
        bundle = checks.Bundle.key({"log": [{"kind": "command", "source": "observed", "command": "ls",
                                             "exit_code": 0, "output": ""},
                                            {"kind": "command", "source": "inferred", "command": "git push",
                                             "exit_code": 0, "output": ""}]})
        reader = {"pushed": checks.Check(lambda bundle: ("pass", str(len(bundle.entries("command")))), {})}
        verdict = checks.decide("pushed", bundle, {}, reader)  # a check that reads the log, through its one door
        self.assertEqual(verdict["outcome"], "undecidable")
        self.assertIn("inferred, not observed", verdict["reason"])
        self.assertIs(verdict["inferred"], True)  # counted as inferred evidence in the label file
        unsure = {"unsure": checks.Check(lambda bundle: ("undecidable", "no output to read"), {})}
        self.assertIs(checks.decide("unsure", bundle, {}, unsure)["inferred"], False)

    def test_an_undecided_verdict_says_whether_the_grader_view_hides_what_left_it_so(self):
        overlay = {"skill": "haiku-writer", "paths": ["skills/haiku-writer"]}
        tests, script = "python3 -m unittest discover -s tests", "timeout 60 python3 skills/haiku-writer/scripts/x.py"
        script_ran = {"pattern": r"python3 \S*x\.py", "ran": False}
        for command, args, hidden in (
                (script, script_ran, True), ("time python3 scripts/x.py", script_ran, False),
                (f"{tests}; {script}", {"pattern": r"python3 -m unittest", "ran": True, "exit_code": 0}, False),
                (f"{tests}; {script}", script_ran, True),  # its match is cut away
                (f"cd skills/haiku-writer; time {tests}", {"pattern": r"python3 -m unittest", "ran": True}, True)):
            log = [{"kind": "command", "source": "observed", "command": command, "exit_code": 0, "output": ""}]
            bundle = checks.Bundle({"files_after": {}, "diff": {}, "log": log, "final_message": None,
                                    "overlay": overlay}, {}.__getitem__)
            verdict = checks.decide("command_ran", bundle, args)  # it asks the view (`view.shown`) what it shows
            with self.subTest(command=command, args=args):
                self.assertEqual((verdict["outcome"], verdict["hidden"]), ("undecidable", hidden))
        log = [{"kind": "command", "source": "observed", "command": "time python3 scripts/x.py", "exit_code": 0,
                "output": ""}]
        key = checks.Bundle.key({"log": log})  # an answer key has no overlay, so the view hides nothing of it
        self.assertIs(checks.decide("command_ran", key, {"pattern": r"python3 \S*x\.py", "ran": False})["hidden"],
                      False)

    def test_a_broken_check_or_wrong_arguments_stop_the_round(self):
        bundle = checks.Bundle.key({})
        for path in ("./a", "a//b", "a/", "a/./b", "../a", "/a", ""):  # one spelling of a world path, never a typo
            with self.subTest(path=path), self.assertRaisesRegex(checks.CheckError, "of their shape"):
                checks.decide("file_state", bundle, {"path": path, "state": "absent"})
        for args, reason in (({"path": "a"}, "unknown or missing"), ({"path": "a", "state": "gone"}, "of their shape"),
                             ({"path": "a", "state": "absent", "more": 1}, "unknown or missing")):
            with self.subTest(args=args), self.assertRaisesRegex(checks.CheckError, reason):
                checks.decide("file_state", bundle, args)
        for name, args in (("command_ran", {"pattern": "(", "ran": True}),
                           ("sections", {"headings": ["A"], "level": 7}),
                           ("shares_words", {"source": "a", "run": 0, "shared": True}),
                           ("frontmatter", {"required": [], "file": "a"}),
                           ("no_shared_words", {"source": "a", "run": 8, "written": []}),
                           ("no_shared_words", {"source": "a", "run": 6, "written": ["b"], "lines": [3, 2]}),
                           ("no_shared_words", {"source": "a", "run": 6, "written": ["b"], "lines": [0]}),
                           ("no_shared_words", {"source": "a", "run": 6, "written": ["b"], "lines": []}),
                           ("field_words", {"field": "description", "most": 0})):
            with self.subTest(check=name), self.assertRaisesRegex(checks.CheckError, "of their shape"):
                checks.decide(name, bundle, args)
        with self.assertRaisesRegex(checks.CheckError, "no check is named"):
            checks.decide("no_such_check", bundle, {})
        broken = {"boom": checks.Check(lambda bundle: 1 / 0, {}),
                  "vague": checks.Check(lambda bundle: ("maybe", "x"), {}),
                  "silent": checks.Check(lambda bundle: ("pass", ""), {})}
        for name, reason in (("boom", "failed to run: ZeroDivisionError"), ("vague", "not an outcome"),
                             ("silent", "not an outcome")):
            with self.subTest(check=name), self.assertRaisesRegex(checks.CheckError, reason):
                checks.decide(name, bundle, {}, broken)

    def test_an_own_check_script_that_runs_too_long_leaves_it_undecidable(self):
        import contain, internal, subprocess
        too_long = subprocess.TimeoutExpired("bwrap", 600)
        with mock.patch.object(contain, "available", return_value=None), \
                mock.patch.object(internal, "read_pinned"), mock.patch("subprocess.run", side_effect=too_long):
            verdict = checks.decide("own_release_checks", checks.Bundle.key({}), {})
        self.assertEqual(verdict["outcome"], "undecidable")
        self.assertIn("ran past 600 seconds", verdict["reason"])

    def test_a_library_module_outside_its_rule_is_refused(self):
        folder = self.tmp / "library"
        folder.mkdir()
        (folder / "a.py").write_text("from checks import Check\nCHECKS = {'x': Check(lambda b: ('pass', 'y'), {})}\n")
        (folder / "b.py").write_text("from checks import Check\nCHECKS = {'x': Check(lambda b: ('pass', 'y'), {})}\n")
        with self.assertRaisesRegex(checks.CheckError, "defined twice"):
            checks.library(folder)
        (folder / "b.py").write_text("CHECKS = {'z': print}\n")
        with self.assertRaisesRegex(checks.CheckError, "not a mapping of names to Checks"):
            checks.library(folder)
