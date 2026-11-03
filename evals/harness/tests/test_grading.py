"""Grading: only what no check decided goes to the graders, a grader reads one page written from the grader view,
and a grading file is accepted only when every answer holds and quotes that page word for word."""

import hashlib
import json

from helpers import JUDGED, TempCase, expect

import grading
import host
import view

UNDECIDABLE = {"check": "file_state", "outcome": "undecidable", "reason": "an inferred read"}
PASSED = {"check": "file_state", "outcome": "pass", "reason": "it exists"}
CHECK = {"name": "file_state", "args": {"path": "a.md", "state": "exists"}}


def record(files, log, final="Done."):
    """A bundle record of a run that changed nothing, with `files` ({path: bytes or ("link", target)})."""
    blobs, entries = {}, {}
    for path, data in files.items():
        if isinstance(data, tuple):
            entries[path] = "link " + data[1]
        else:
            digest = hashlib.sha256(data).hexdigest()
            blobs[digest], entries[path] = data, f"file {digest}"
    entries["docs"] = "dir"
    return {"overlay": {"skill": "haiku-writer", "paths": ["skills/haiku-writer"], "index": "AGENTS.md",
                        "index_without": None},
            "folders": {}, "own_files": [], "files_after": entries, "diff": {}, "final_message": final,
            "case": None, "mode": "task", "log": log}, blobs.__getitem__


class Answers(TempCase):
    def test_the_check_gives_the_outcome_of_each_answer_key_for_its_reason(self):
        self.assertEqual(grading.prove(), {})

    def test_the_keys_hold_a_key_of_each_outcome_and_the_page_they_share(self):
        given, shared = grading.keys()
        self.assertEqual({data["outcome"] for data in given.values()}, {"pass", "fail"})
        self.assertIn("# Final message", shared)
        self.assertEqual(sorted(p.name for p in grading.KEYS.iterdir() if p.suffix != ".json"), ["page.md"])

    def test_keys_without_one_that_must_fail_are_refused(self):
        (self.tmp / "page.md").write_text("x\n")
        (self.tmp / "one.json").write_text(json.dumps({"ids": [], "grading": {"answers": []}, "outcome": "pass"}))
        with self.assertRaisesRegex(grading.GradingError, "must fail"):
            grading.prove(self.tmp)
        (self.tmp / "two.json").write_text(json.dumps({"ids": [], "grading": {}, "outcome": "fail"}))
        with self.assertRaisesRegex(grading.GradingError, "problem"):
            grading.keys(self.tmp)


class Questions(TempCase):
    def test_only_what_no_check_decided_goes_to_the_graders(self):
        expectations = [expect("a"), expect("b", check=CHECK), expect("c", check=CHECK)]
        asked = grading.questions(expectations, [None, PASSED, UNDECIDABLE])
        self.assertEqual([question["id"] for question in asked], ["q1", "q3"])
        self.assertEqual(asked[0], {"id": "q1", **JUDGED})

    def test_a_verdict_is_given_exactly_for_each_expectation_with_a_check(self):
        for expectations, verdicts in (([expect("a")], []), ([expect("a")], [PASSED]),
                                       ([expect("b", check=CHECK)], [None])):
            with self.subTest(verdicts=verdicts), self.assertRaises(grading.GradingError):
                grading.questions(expectations, verdicts)

    def test_every_expectation_of_every_case_can_be_asked(self):
        import cases
        for case in cases.load_cases("claims-writer"):
            expectations = case.data["expectations"]
            verdicts = [UNDECIDABLE if "check" in item else None for item in expectations]
            asked = grading.questions(expectations, verdicts)
            self.assertEqual([q["id"] for q in asked], [f"q{n}" for n in range(1, len(expectations) + 1)])


class Page(TempCase):
    def page(self, files, log, final="Done."):
        return grading.page(*view.view(*record(files, log, final)))

    def test_the_page_shows_what_the_agent_did_and_wrote_and_never_what_a_command_printed(self):
        shown = self.page({"notes.md": b"Tests pass.\n", "logo.png": b"\x89PNG\xff", "latest": ("link", "notes.md")},
                          [host.entry("command", command="go test ./...", exit_code=0, output="ok  limiter 0.2s"),
                           host.entry("read", path="notes.md"), host.entry("message", text="Done.")])
        for seen in ("go test ./...", "Tests pass.", "(not text, 5 bytes)", "(a link to notes.md)", "## docs",
                     "(a folder)", '- read (observed): {"path": "notes.md"}'):
            self.assertIn(seen, shown)
        for unseen in ("ok  limiter", "exit_code", "0.2s"):
            self.assertNotIn(unseen, shown)

    def test_the_page_never_shows_the_skill(self):
        shown = self.page({"AGENTS.md": b"| haiku-writer | skills/haiku-writer/SKILL.md |\nRules.\n"},
                          [host.entry("command", command="cat skills/haiku-writer/SKILL.md", exit_code=0, output=""),
                           host.entry("skill", name="haiku-writer")], final="I used haiku-writer.\nDone.")
        self.assertNotIn("haiku-writer", shown)
        self.assertIn("Rules.", shown)

    def test_a_quote_of_the_page_is_accepted_and_one_of_a_command_s_output_is_not(self):
        shown = self.page({"notes.md": b"The limit is\n100 requests.\n"},
                          [host.entry("command", command="go test ./...", exit_code=0, output="ok  limiter")])
        answers = [{"id": "q1", "answer": "yes", "evidence": "The limit is 100 requests."},
                   {"id": "q2", "answer": "no", "evidence": "go test ./..."}]
        self.assertEqual(grading.check({"answers": answers}, ["q1", "q2"], shown), [])
        answers[1]["evidence"] = "ok  limiter"
        self.assertEqual(len(grading.check({"answers": answers}, ["q1", "q2"], shown)), 1)
