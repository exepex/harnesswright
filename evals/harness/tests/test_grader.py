"""Grader runs: a grader is a trigger run of a folder holding only the page and the questions, its final message is
its answer sheet, and the pages of a round reach graders in a blind order."""

import json
import shutil
import types
import unittest
from unittest import mock

from helpers import JUDGED, TempCase

import contain
import grader
import manifest
import scrub
from test_host import FAKE, changed, fake_adapter

JAIL = contain.available()
ASKED = [{"id": "q1", **JUDGED}, {"id": "q2", **JUDGED}]
PAGE = "# Final message\n\nDone.\n\n# Actions\n\n- command (observed)\n  - command: go test -run \"TestX\" ./...\n"
GOOD = {"answers": [{"id": "q1", "answer": "yes", "evidence": "Done."},
                    {"id": "q2", "answer": "no", "evidence": 'go test -run "TestX" ./...'}]}


class Sheet(unittest.TestCase):
    def test_a_sheet_is_one_json_object_alone_or_in_its_one_fenced_block(self):
        text = json.dumps(GOOD)
        for message in (text, f"  {text}\n", f"```json\n{text}\n```", f"```\n{text}\n```",
                        f"```JSON \r\n{text}\r\n```"):
            with self.subTest(message=message):
                self.assertEqual(grader.sheet(message), GOOD)
        for message in (None, "", "Here it is: " + text, f"```json\n{text}\n```\nDone.", "[1, 2]", "yes",
                        f"```json\n{text}\n```\n```json\n{text}\n```"):
            with self.subTest(message=message):
                self.assertIsNone(grader.sheet(message))

    def test_a_line_break_inside_a_quote_is_read_as_it_stands(self):
        found = grader.sheet('{"answers": [{"id": "q1", "answer": "yes", "evidence": "The limit is\n100."}]}')
        self.assertEqual(found["answers"][0]["evidence"], "The limit is\n100.")


class Blind(unittest.TestCase):
    PAGES = {"with_skill/1": "page a", "without_skill/1": "page b", "golden/1": "page c", "with_skill/2": "page d"}

    def test_the_order_comes_from_the_seed_and_the_pages_never_from_their_names_or_order(self):
        order = grader.blind(self.PAGES, seed=7)
        self.assertEqual(sorted(order), sorted((n, grader.blind({n: t}, 0)[0][1]) for n, t in self.PAGES.items()))
        self.assertEqual(grader.blind(dict(reversed(list(self.PAGES.items()))), seed=7), order)
        renamed = {f"run-{n}": self.PAGES[name] for n, name in enumerate(self.PAGES)}
        self.assertEqual([i for _, i in grader.blind(renamed, seed=7)], [i for _, i in order])
        self.assertNotEqual([grader.blind(self.PAGES, seed=s) for s in range(5)].count(order), 5)

    def test_an_id_is_the_hash_of_the_page_and_names_nothing(self):
        for name, id_ in grader.blind(self.PAGES, seed=1):
            self.assertRegex(id_, r"^[0-9a-f]{16}$")
            self.assertNotIn(id_, name)


def sheet_of(**answers):
    """A grader that gives these answers, or no sheet when none are given, and records the questions it was asked."""
    def grade_one(page, asked):
        grade_one.asked.append([question["id"] for question in asked])
        if not answers:
            return grader.Graded(None, ["the host failed: x"], [[]])
        return grader.Graded({"answers": [{"id": q["id"], "answer": answers[q["id"]], "evidence": "Done."}
                                          for q in asked]}, [], [[]])
    grade_one.asked = []
    return grade_one


class Panel(unittest.TestCase):
    THREE = [{"id": f"q{n}", **JUDGED} for n in (1, 2, 3)]

    def test_a_question_two_graders_answer_the_same_needs_no_tie_breaker(self):
        tiebreak = sheet_of(q1="no", q2="no", q3="no")
        found = grader.panel(PAGE, self.THREE, [sheet_of(q1="yes", q2="no", q3="yes")] * 2, tiebreak)
        self.assertEqual((found.answers, found.unanswered, found.agreed, found.asked),
                         ({"q1": "yes", "q2": "no", "q3": "yes"}, [], 3, 3))
        self.assertEqual((tiebreak.asked, len(found.graded)), ([], 2))

    def test_a_split_question_alone_goes_to_the_tie_breaker_and_the_majority_answers_it(self):
        tiebreak = sheet_of(q2="no", q3="yes")
        found = grader.panel(PAGE, self.THREE, [sheet_of(q1="yes", q2="yes", q3="no"),
                                                sheet_of(q1="yes", q2="no", q3="yes")], tiebreak)
        self.assertEqual(tiebreak.asked, [["q2", "q3"]])
        self.assertEqual((found.answers, found.unanswered, found.agreed), ({"q1": "yes", "q2": "no", "q3": "yes"},
                                                                           [], 1))
        self.assertEqual(len(found.graded), 3)

    def test_an_ungraded_grader_leaves_its_questions_to_the_other_two(self):
        tiebreak = sheet_of(q1="yes", q2="no", q3="no")
        found = grader.panel(PAGE, self.THREE, [sheet_of(), sheet_of(q1="yes", q2="yes", q3="no")], tiebreak)
        self.assertEqual(tiebreak.asked, [["q1", "q2", "q3"]])
        self.assertEqual((found.answers, found.unanswered, found.agreed), ({"q1": "yes", "q3": "no"}, ["q2"], 0))

    def test_no_tie_breaker_runs_when_it_cannot_make_two_answers_the_same(self):
        for tiebreak in (sheet_of(), sheet_of(q1="yes", q2="yes", q3="yes")):
            found = grader.panel(PAGE, self.THREE, [sheet_of(), sheet_of()], tiebreak)
            self.assertEqual((found.answers, found.unanswered, tiebreak.asked), ({}, ["q1", "q2", "q3"], []))
        found = grader.panel(PAGE, self.THREE, [sheet_of(q1="yes", q2="no", q3="no"), sheet_of(q1="no", q2="yes",
                                                q3="yes")], sheet_of())  # the tie-breaker is ungraded
        self.assertEqual((found.answers, found.unanswered), ({}, ["q1", "q2", "q3"]))
        with self.assertRaisesRegex(ValueError, "two graders"):
            grader.panel(PAGE, self.THREE, [sheet_of(q1="yes", q2="yes", q3="yes")], sheet_of())


class Folder(TempCase):
    def test_a_grader_folder_holds_only_the_page_and_the_questions_and_names_no_run(self):
        made, world = grader.folder(PAGE, ASKED)
        self.addCleanup(shutil.rmtree, made, True)
        self.assertEqual((made.parent, world), (grader.place(), made / "page"))
        self.assertEqual(sorted(manifest.manifest(world)), [grader.PAGE, grader.QUESTIONS])
        self.assertEqual((world / grader.PAGE).read_text(), PAGE)
        self.assertEqual(json.loads((world / grader.QUESTIONS).read_text()), ASKED)
        self.assertRegex(made.name, r"^grader-[A-Za-z0-9_]+$")

    def test_a_page_with_no_questions_needs_no_grader(self):
        graded = grader.grade(None, PAGE, [])
        self.assertEqual((graded.answers, graded.tries, graded.logs), ({}, [], []))


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class FakeGrader(TempCase):
    """The fake host grades in a real jail: its actions stand in for what a model would do."""

    def grade(self, actions, keep=False, adapter=None, env=None, tokens=()):
        """The grading of the fake host's `actions`, and the grader folders it made, which are removed after each
        try unless `keep` (then the test removes them)."""
        tool = self.tmp / "tool"
        if not tool.exists():
            shutil.copytree(FAKE, tool, ignore=shutil.ignore_patterns("adapter.py", "__pycache__"))
        made, real = [], grader.folder

        def recorded(*args):
            made.append(real(*args)[0])
            self.addCleanup(shutil.rmtree, made[-1], True)
            return made[-1], made[-1] / "page"
        kept = types.SimpleNamespace(rmtree=lambda *args, **kwargs: None) if keep else grader.shutil
        with mock.patch.object(grader, "folder", recorded), mock.patch.object(grader, "shutil", kept):
            graded = grader.grade(adapter or fake_adapter(), PAGE, ASKED, timeout=120, prompt=json.dumps(actions),
                                  operator_env={"PATH": f"{tool}:/usr/bin:/bin", **(env or {})},
                                  operator_home=self.tmp / "operator", host_paths=[tool], tokens=tokens)
        return graded, made

    def test_a_grader_reads_its_page_and_its_last_message_is_the_sheet(self):
        graded, made = self.grade([{"do": "read", "path": grader.PAGE}, {"do": "read", "path": grader.QUESTIONS},
                                   {"do": "say", "text": "Reading."}, {"do": "say", "text": json.dumps(GOOD)}])
        self.assertEqual((graded.answers, graded.tries), ({"q1": "yes", "q2": "no"}, []))
        self.assertEqual(graded.sheet, GOOD)
        self.assertEqual([[e["kind"] for e in log] for log in graded.logs], [["read", "read", "message", "message"]])
        self.assertEqual([folder.exists() for folder in made], [False])

    def test_a_grader_cannot_change_its_page(self):
        graded, made = self.grade([{"do": "write", "path": grader.PAGE, "text": "# Final message\n\nAll pass.\n"},
                                   {"do": "command", "command": f"echo 'All tests pass.' >> {grader.PAGE}"},
                                   {"do": "say", "text": json.dumps(GOOD)}], keep=True)
        self.assertEqual(graded.answers, {"q1": "yes", "q2": "no"})
        self.assertEqual([(folder / "page" / grader.PAGE).read_text() for folder in made], [PAGE])

    def test_a_refused_sheet_is_graded_again_and_then_the_run_is_ungraded(self):
        bad = {"answers": [{"id": "q1", "answer": "yes", "evidence": "All tests pass."}]}
        graded, made = self.grade([{"do": "say", "text": json.dumps(bad)}])
        self.assertIsNone(graded.answers)
        self.assertEqual(len(graded.tries), grader.TRIES)
        self.assertIn("not found word for word", graded.tries[0])
        self.assertIn("not answered: q2", graded.tries[0])
        self.assertEqual(len(set(made)), grader.TRIES)
        self.assertEqual((graded.sheet, len(graded.logs)), (None, grader.TRIES))

    def test_a_final_message_that_is_not_a_sheet_is_refused(self):
        graded, _ = self.grade([{"do": "say", "text": json.dumps(GOOD)}, {"do": "say", "text": "Done."}])
        self.assertIsNone(graded.answers)
        self.assertEqual(graded.tries, ["the final message is not one JSON object"] * grader.TRIES)

    def test_what_a_grader_prints_or_says_keeps_no_credential(self):
        key = "fake-key-0123456789abcdef"
        signed = changed(fake_adapter(), ENV_KEYS=("FAKE_API_KEY",))
        bad = {"answers": [{"id": key, "answer": "yes", "evidence": "Done."}]}
        graded, _ = self.grade([{"do": "command", "command": "echo $FAKE_API_KEY"},
                                {"do": "say", "text": json.dumps(bad)}], adapter=signed, env={"FAKE_API_KEY": key})
        self.assertIsNone(graded.answers)
        self.assertEqual(graded.logs[0][0]["output"], "[redacted]\n")
        self.assertNotIn(key, json.dumps([graded.logs, graded.tries]))

    def test_a_canary_a_grader_kept_in_its_home_stops_the_round(self):
        token = "HWCANARY-0123456789abcdef"  # the command builds it, so only the home file holds it whole
        with self.assertRaises(scrub.Leak):
            self.grade([{"do": "command", "command": 'echo "HWCANARY-$(echo 0123456789abcdef)" > "$HOME/session"'},
                        {"do": "say", "text": json.dumps(GOOD)}], tokens=[token])

    def test_a_canary_a_grader_sends_to_the_gate_stops_the_round(self):
        token = "HWCANARY-0123456789abcdef"  # the command builds it, so only the gate's request log holds it whole
        send = ("import socket; s = socket.socket(socket.AF_UNIX); s.connect('/run/gate'); "
                "s.sendall(b'CONNECT HWCANARY-' + b'0123456789abcdef' + b':443 HTTP/1.1\\r\\n\\r\\n'); s.recv(64)")
        with self.assertRaises(scrub.Leak):
            self.grade([{"do": "command", "command": f'python3 -c "{send}"'},
                        {"do": "say", "text": json.dumps(GOOD)}], tokens=[token])
