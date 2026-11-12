"""The grade gate: what no check decided goes to blind panels of graders with the goldens mixed in, and a run's
answer counts only where the goldens of its expectation got their settled answers."""

import json
import shutil
import tempfile
import unittest

from test_gates import EXPECTATIONS, Gated
from test_runs import DRIFT

import checks
import evidence
import gates
import goldens
import grader
import grades
import rounds

POND, HELLO = "An old silent pond\n", "Hello\n"


def settled(q2):
    return {f"q{n}": {"expectation": e["text"], "sha256": goldens.fingerprint(e), "answer": answer, "by": "judge-a"}
            for n, (e, answer) in enumerate(zip(EXPECTATIONS, ["yes", q2, "no"]), start=1)}


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


class Graded(Gated):
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
                bundle = str(evidence.store(record, blobs, folder / "bundle"))
                r.runs.append({"key": f"k{number}", "skill": "haiku-writer", "case": "c1", "status": "made",
                               "bundle": bundle})
        return step

    def graded(self, poems, grade):
        self.planned()
        steps = (("run", self.ran(poems)), ("check", gates.check_gate), ("grade", grades.grade_gate))
        return self.go(steps, grade=grade)["gates"][2]["outcome"]

    def grades(self, key):
        return json.loads((self.store / "r1" / "runs" / key / "grades.json").read_text())

    def test_what_no_check_decided_is_answered_where_the_goldens_were_and_kept_beside_the_bundle(self):
        calls = []
        outcome = self.graded([POND, HELLO], answering(pond, calls))
        self.assertIsNone(outcome["goldens"]["haiku-writer/c1"]["q2"])  # both goldens got their settled answer
        self.assertEqual([run["answered"] for run in outcome["runs"]], [["q2"], ["q2"]])
        self.assertEqual(self.grades("k1")["answers"], {"q2": "yes"})
        self.assertEqual(self.grades("k2")["answers"], {"q2": "no"})
        self.assertEqual((self.grades("k1")["agreed"], self.grades("k1")["asked"]), (1, 1))
        self.assertEqual(len(self.grades("k1")["graders"]), 2)  # no tie, so no tie-breaker
        # Two runs and two goldens, each graded by two fresh graders with the host's model, on q2 alone.
        self.assertEqual(calls, [("named-model", ["q2"])] * 8)

    def test_a_run_stays_ungraded_on_a_question_whose_goldens_were_missed(self):
        outcome = self.graded([POND], answering(lambda page: "yes"))
        self.assertIn("a golden was missed: no got yes, not no", outcome["goldens"]["haiku-writer/c1"]["q2"])
        self.assertEqual(outcome["runs"][0]["untrusted"], ["q2"])
        found = self.grades("k1")
        self.assertEqual(found["answers"], {})
        self.assertIn("a golden was missed", found["untrusted"]["q2"])

    def test_a_case_with_no_goldens_is_never_trusted(self):
        for path in self.goldens.iterdir():
            path.unlink()
        outcome = self.graded([POND], answering(pond))
        self.assertEqual(outcome["runs"][0]["untrusted"], ["q2"])
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
        self.assertEqual((found["answers"], found["unanswered"]), ({}, ["q2"]))
        self.assertEqual(found["graders"][0]["tries"], ["the host failed: planted"])

    def test_a_golden_that_cannot_be_built_stops_the_round(self):
        self.golden("bad", {**wrote(POND), "changes": {"README.md/poem.md": POND}})
        with self.assertRaisesRegex(rounds.RoundError, "stopped at the grade gate: .*bad: not a file of the world"):
            self.graded([POND], answering(pond))

    def test_the_reference_host_breaks_ties_when_it_passed_its_probes(self):
        self.assertEqual(grades.reference({"codex": {}, "claude-code": {}}), "claude-code")
        self.assertEqual(grades.reference({"codex": {}, "other": {}}), "codex")


if __name__ == "__main__":
    unittest.main()
