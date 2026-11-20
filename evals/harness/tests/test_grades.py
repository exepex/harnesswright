"""The grade gate: what no check decided goes to blind panels of graders with the goldens mixed in, and a run's
answer counts only where the goldens of its expectation got their settled answers."""

import json
import shutil
import tempfile
import unittest

from test_gates import EXPECTATIONS, Gated
from test_runs import DRIFT

import cases
import checks
import evidence
import gates
import goldens
import grader
import grades
import rounds

POND, HELLO = "An old silent pond\n", "Hello\n"


def settled(q2):
    """Settled answers for every expectation of the case, the done question last: the run says it is done only
    when its poem is the one the case asks for."""
    return {f"q{n}": {"expectation": e["text"], "sha256": goldens.fingerprint(e), "answer": answer, "by": "judge-a"}
            for n, (e, answer) in enumerate(zip([*EXPECTATIONS, cases.done()], ["yes", q2, "no", q2]), start=1)}


def wrote(poem, q2="yes"):
    """A golden's data: the run wrote `poem` to poem.md and said it was done."""
    return {"changes": {"poem.md": poem}, "settled": settled(q2),
            "log": [{"kind": "write", "source": "observed", "path": "poem.md", "sha256": None},
                    {"kind": "message", "source": "observed", "text": "Done."}]}


def answering(rule, calls=None):
    """A stand-in for `grader.grade`: it answers every question by `rule(page)`, quoting the page's first line, and
    records the host model and questions of each call in `calls`."""
    def grade(adapter, page, asked, model=None, timeout=None, **containment):
        if calls is not None:
            calls.append((model, [question["id"] for question in asked]))
        quote = page.splitlines()[0]
        return grader.Graded({"answers": [{"id": q["id"], "answer": rule(page), "evidence": quote} for q in asked]},
                             [], [[]])
    return grade


def pond(page):
    return "yes" if "silent pond" in page else "no"


class Pages(Gated):
    """A round of one case with two goldens, its runs stored as a round stores them."""

    def setUp(self):
        super().setUp()
        shutil.copytree(checks.LIBRARY, self.repo / "evals" / "checks",
                        ignore=shutil.ignore_patterns("keys", "__pycache__"))
        (self.case_dir / "case.json").write_text(json.dumps({"prompt": "Write a haiku.", "kind": "task",
                                                             "expectations": EXPECTATIONS}))
        self.goldens = self.repo / "evals" / "goldens" / "haiku-writer" / "c1"
        self.goldens.mkdir(parents=True)
        self.golden("yes", wrote(POND))
        self.golden("no", wrote(HELLO, "no"))

    def golden(self, name, data):
        (self.goldens / f"{name}.json").write_text(json.dumps(data))

    def ran(self, poems):
        """A probe and run gate that give the fake host and one made run for each of `poems`."""
        def step(r):
            r.hosts["fakehost"] = {"drift": DRIFT}
            case = r.cases[("haiku-writer", "c1")]
            for number, poem in enumerate(poems, start=1):
                folder = self.store / "r1" / "runs" / f"k{number}"
                made = tempfile.mkdtemp(dir=self.tmp)
                record, blobs = goldens.bundle(goldens.Golden("run", wrote(poem)), case, r.modules["fakehost"],
                                               made, DRIFT, "fakehost 1.0", "named-model", self.repo / "skills")
                kept = folder / "bundle"  # kept when the round runs again, as a run is
                bundle = str(kept if kept.is_dir() else evidence.store(record, blobs, kept))
                r.runs.append({"key": f"k{number}", "skill": "haiku-writer", "case": "c1", "status": "made",
                               "bundle": bundle})
        return step

    def graded(self, poems, grade):
        self.planned()
        steps = (("run", self.ran(poems)), ("check", gates.check_gate), ("grade", grades.grade_gate))
        return self.go(steps, grade=grade)["gates"][2]["outcome"]

    def grades(self, key, kind="runs"):
        """The record the one attempt of the round wrote of the page `key`."""
        [attempt] = (self.store / "r1" / "grades").iterdir()
        return json.loads((attempt / kind / f"{key}.json").read_text())


class Graded(Pages):
    def test_what_no_check_decided_is_answered_where_the_goldens_were_and_kept_beside_the_bundle(self):
        calls = []
        outcome = self.graded([POND, HELLO], answering(pond, calls))
        self.assertIsNone(outcome["goldens"]["haiku-writer/c1"]["q2"])  # both goldens got their settled answer
        # q2 and the done question, q4, which every task run is asked
        self.assertEqual([run["answered"] for run in outcome["runs"]], [["q2", "q4"], ["q2", "q4"]])
        self.assertEqual(self.grades("k1")["answers"], {"q2": "yes", "q4": "yes"})
        self.assertEqual(self.grades("k2")["answers"], {"q2": "no", "q4": "no"})
        self.assertEqual((self.grades("k1")["agreed"], self.grades("k1")["asked"]), (2, ["q2", "q4"]))
        self.assertEqual([(g["host"], g["model"]) for g in self.grades("k1")["graders"]],
                         [("fakehost", "named-model")] * 2)  # no tie, so no tie-breaker
        self.assertEqual({name: len(self.grades("k1")[name]) for name in ("page", "questions")},
                         {"page": 64, "questions": 64})  # what was graded, so a rebuilt page can be matched to it
        self.assertEqual(self.grades("k1")["graders"][0]["costs"], [])
        self.assertEqual(self.grades("k1")["case"], "haiku-writer/c1")
        golden = self.grades("haiku-writer/c1/no", "goldens")  # every graded page leaves the same record
        self.assertEqual((golden["asked"], golden["answers"], golden["settled"]),
                         (["q2", "q4"], {"q2": "no", "q4": "no"}, {"q2": "no", "q4": "no"}))
        self.assertEqual(outcome["goldens"], {"haiku-writer/c1": {"q2": None, "q4": None}})  # what a page was asked
        # Two runs and two goldens, each graded by two fresh graders with the host's model, on q2 and q4 alone.
        self.assertEqual(calls, [("named-model", ["q2", "q4"])] * 8)

    def test_a_run_stays_ungraded_on_a_question_whose_goldens_were_missed(self):
        outcome = self.graded([POND], answering(lambda page: "yes"))
        self.assertIn("a golden was missed: no got yes, not no", outcome["goldens"]["haiku-writer/c1"]["q2"])
        self.assertEqual(outcome["runs"][0]["untrusted"], ["q2", "q4"])
        found = self.grades("k1")
        self.assertEqual(found["answers"], {})
        self.assertIn("a golden was missed", found["untrusted"]["q2"])

    def test_a_golden_whose_retry_flipped_is_a_miss_named_as_flipped(self):
        def flipping(adapter, page, asked, model=None, timeout=None, **containment):
            found = answering(pond)(adapter, page, asked)
            if HELLO.strip() in page:  # the golden settled `no`: each grader was refused once for a `yes` to q2
                found.offered.append({"q2": "yes"})
            return found

        outcome = self.graded([POND], flipping)
        self.assertEqual(outcome["goldens"]["haiku-writer/c1"]["q2"],
                         "a golden was missed: no got flipped retry, not no")
        self.assertEqual(self.grades("haiku-writer/c1/no", "goldens")["flipped"], ["q2"])
        self.assertEqual(outcome["runs"][0]["untrusted"], ["q2"])

    def test_a_case_with_no_goldens_is_never_trusted(self):
        for path in self.goldens.iterdir():
            path.unlink()
        outcome = self.graded([POND], answering(pond))
        self.assertEqual(outcome["runs"][0]["untrusted"], ["q2", "q4"])
        self.assertIn("no golden", self.grades("k1")["untrusted"]["q2"])

    def test_a_split_goes_to_the_tie_breaker_and_a_question_with_no_two_answers_the_same_stays_unanswered(self):
        seen = {}

        def split(adapter, page, asked, model=None, timeout=None, **containment):
            seen[page] = seen.get(page, -1) + 1  # its two graders answer two ways, the tie-breaker yes; a run and a
            # golden may have the same page
            return answering(lambda page: ["yes", "no", "yes"][seen[page] % 3])(adapter, page, asked)

        self.graded([POND], split)
        found = self.grades("k1")
        self.assertEqual(len(found["graders"]), 3)
        self.assertEqual(found["agreed"], 0)

        def broken(adapter, page, asked, model=None, timeout=None, **containment):
            return grader.Graded(None, ["the host failed: planted"], [[]])

        self.store = self.tmp / "store2"
        self.planned()
        steps = (("run", self.ran([POND])), ("check", gates.check_gate), ("grade", grades.grade_gate))
        self.go(steps, grade=broken)
        found = self.grades("k1")
        self.assertEqual((found["answers"], found["unanswered"]), ({}, ["q2", "q4"]))
        self.assertEqual(found["graders"][0]["tries"], ["the host failed: planted"] * 2)  # its fresh grader's too

    def test_each_attempt_keeps_its_own_grading(self):
        self.graded([POND], answering(pond))
        steps = (("run", self.ran([POND])), ("check", gates.check_gate), ("grade", grades.grade_gate))
        self.go(steps, grade=answering(lambda page: "yes"))  # the round run again, its goldens missed this time
        found = [json.loads((attempt / "runs" / "k1.json").read_text())["answers"]
                 for attempt in (self.store / "r1" / "grades").iterdir()]
        self.assertCountEqual(found, [{}, {"q2": "yes", "q4": "yes"}])

    def test_a_kept_grade_is_not_made_again_on_resume_and_counts_only_while_its_graders_are_trusted(self):
        self.graded([POND], answering(pond))
        kept = (self.store / "r1" / grades.KEPT / "k1.json").read_text()
        self.assertEqual(json.loads(kept)["trusted"], {"q2": None, "q4": None})  # the goldens it was graded under
        calls, steps = [], (("run", self.ran([POND])), ("check", gates.check_gate), ("grade", grades.grade_gate))
        outcome = self.go(steps, grade=answering(pond, calls))["gates"][2]["outcome"]
        self.assertEqual(len(calls), 4)  # the two goldens, graded again by two graders each; the run's page is not
        self.assertEqual((outcome["runs"][0]["answered"], outcome["runs"][0]["graded_in"]),
                         (["q2", "q4"], json.loads(kept)["attempt"]))
        self.assertEqual((self.store / "r1" / grades.KEPT / "k1.json").read_text(), kept)  # never replaced
        lost = self.go(steps, grade=answering(lambda page: "yes"))["gates"][2]["outcome"]  # its graders lose trust
        self.assertEqual((lost["runs"][0]["answered"], lost["runs"][0]["untrusted"]), ([], ["q2", "q4"]))
        self.assertEqual((self.store / "r1" / grades.KEPT / "k1.json").read_text(), kept)
        record = json.loads(kept)
        (self.store / "r1" / grades.KEPT / "k1.json").write_text(json.dumps({**record, "page": "0" * 64}))
        with self.assertRaisesRegex(rounds.RoundError, "the kept grade is not of run k1's page and questions"):
            self.go(steps, grade=answering(pond))

    def test_a_golden_that_cannot_be_built_stops_the_round(self):
        self.golden("bad", {**wrote(POND), "changes": {"README.md/poem.md": POND}})
        with self.assertRaisesRegex(rounds.RoundError, "stopped at the grade gate: .*bad: not a file of the world"):
            self.graded([POND], answering(pond))

    def test_the_reference_host_breaks_ties_when_it_passed_its_probes(self):
        self.assertEqual(grades.reference({"codex": {}, "claude-code": {}}), "claude-code")
        self.assertEqual(grades.reference({"codex": {}, "other": {}}), "codex")


if __name__ == "__main__":
    unittest.main()
