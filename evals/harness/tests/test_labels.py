"""The label gate: the labels of 10 · Skills, every number read from what the round stored."""

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from test_gates import JUDGED
from test_grades import HELLO, POND, Pages, answering, pond, wrote
from test_prices import PRICES
from test_runs import DRIFT

import cases
import evidence
import gates
import grader
import goldens
import grades
import labels
import setups

CONTRACT = {"contract": {"path": "README.md", "line": 1, "quote": "# Notes app"}}
EXPECTATIONS = [  # a format check, a contract question for the graders, and a contract check
    {"text": "The poem is written", "source": "format", "judged": JUDGED,
     "check": {"name": "file_state", "args": {"path": "poem.md", "state": "changed"}}},
    {"text": "The poem is a haiku", "source": CONTRACT, "judged": JUDGED},
    {"text": "The notes are kept", "source": CONTRACT, "judged": JUDGED,
     "check": {"name": "file_state", "args": {"path": "README.md", "state": "unchanged"}}},
]


DRAFT = "A first draft\n"


def done_or_pond(adapter, page, asked, model=None, timeout=None, **containment):
    """A stand-in grader: q4, the done question, is yes unless the page is a draft; every other question is yes
    only for the haiku."""
    quote = page.splitlines()[0]
    answers = [{"id": q["id"], "answer": ("no" if DRAFT.strip() in page else "yes") if q["id"] == "q4"
                else pond(page), "evidence": quote} for q in asked]
    return grader.Graded({"answers": answers}, [], [[]])


def case(kind="task", expectations=EXPECTATIONS, **fields):
    return types.SimpleNamespace(skill="haiku-writer", kind=kind, expectations=expectations, **fields)


def verdict(outcome, name="file_state"):
    return {"check": name, "outcome": outcome, "reason": "planted"}


class Gate(Pages):
    """The label gate after the run, check and grade gates, on runs stored as a round stores them."""

    def setUp(self):
        super().setUp()
        (self.case_dir / "case.json").write_text(json.dumps({"prompt": "Write a haiku.", "kind": "task",
                                                             "expectations": EXPECTATIONS}))
        # q2 asks for the haiku, and q4, the done question, whether the run says it is done: the "no" golden wrote
        # the wrong poem and says it is done, a false done; the "draft" golden says it is not done
        for name, poem, answer, done in (("yes", POND, "yes", "yes"), ("no", HELLO, "no", "yes"),
                                         ("draft", DRAFT, "no", "no")):
            data = wrote(poem)
            data["settled"] = {f"q{n}": {"expectation": e["text"], "sha256": goldens.fingerprint(e), "answer": a,
                                         "by": "judge-a"}
                               for n, (e, a) in enumerate(zip([*EXPECTATIONS, cases.done()],
                                                              ["yes", answer, "yes", done]), start=1)}
            self.golden(name, data)
        (self.repo / "evals" / "results").mkdir(parents=True, exist_ok=True)
        (self.repo / "evals" / "results" / "prices.json").write_text(json.dumps(PRICES))

    def stored(self, poems):
        """A probe and run gate that give the fake host and one made run per (arm, poem) of `poems`."""
        def probe(r):  # as the probe gate pins it, with the tools the cases declare
            r.hosts["fakehost"] = {"drift": gates._pin(r.folder / "drift" / "fakehost.json", {"tools": {}, **DRIFT})}
            return {"passed": ["fakehost"], "not run": {}, "drift": {}}

        def run(r):
            case_, made = r.cases[("haiku-writer", "c1")], []
            for number, (arm, poem) in enumerate(poems, start=1):
                out = tempfile.mkdtemp(dir=self.tmp)
                record, blobs = goldens.bundle(goldens.Golden("run", wrote(poem)), case_, r.modules["fakehost"],
                                               out, DRIFT, "fakehost 1.0", "named-model", self.repo / "skills")
                kept = self.store / "r1" / "runs" / f"k{number}" / "bundle"
                bundle = str(kept if kept.is_dir() else evidence.store(record, blobs, kept))
                made.append({"host": "fakehost", "skill": "haiku-writer", "case": "c1", "arm": arm, "number": number,
                             "key": f"k{number}", "status": "made"})
                r.runs.append({**made[-1], "bundle": bundle})
            return made
        return probe, run

    def test_the_label_file_counts_each_scored_run_and_names_what_is_missing(self):
        record = self.planned()
        probe, run = self.stored([("with_skill", POND)] * 3 + [("without_skill", HELLO)] * 3)
        steps = (("probe", probe), ("run", run), ("check", gates.check_gate), ("grade", grades.grade_gate),
                 ("label", labels.label_gate))
        (self.store / "r1" / "attempts").mkdir(parents=True)
        (self.store / "r1" / "attempts" / "20000101T000000-killed.json").write_text("")  # an earlier, killed attempt
        outcome = self.go(steps, grade=done_or_pond)["gates"][-1]["outcome"]
        self.assertEqual(outcome, {"haiku-writer": {"fakehost": "incomplete"}})  # the fixture declares no kind
        [path] = (self.store / "r1" / "labels").iterdir()
        found = json.loads(path.read_text())
        entry = found["skills"]["haiku-writer"]["fakehost"]
        self.assertEqual((entry["task_pass_rate"], entry["baseline_pass_rate"], entry["lift"]), (1.0, 0.0, 1.0))
        self.assertEqual(entry["runs"], {"c1, with_skill": 3, "c1, without_skill": 3})
        self.assertEqual((entry["model"], entry["gaps"]), ("named-model", [
            "kind: none declared in evals/kinds.json", "situations: the skill is not in evals/situations.json",
            "the reference host claude-code was not run"]))  # no trigger case: the trigger label's gap, not this one
        self.assertEqual(entry["trigger"], {"accuracy": None, "threshold": 0.9, "cases": 0, "runs": {},
                                            "inferred_loads": 0, "met": False, "gaps": ["test trigger cases: none"]})
        self.assertEqual(path.stem, found["attempt"])
        self.assertEqual(found["no_reason"], ["20000101T000000-killed"])  # the label file names it
        self.assertEqual(found["shipped"], {"haiku-writer": False})  # decided here, on the reference host's labels
        self.assertEqual(sorted(found["agreement"]["questions"]), ["haiku-writer/c1 q2", "haiku-writer/c1 q4"])
        # the setup that measured the skill: the one fingerprint its results compare by (doc 12, One setup)
        own = {"c1": cases.Case(self.case_dir, "haiku-writer")}
        self.assertEqual(found["setups"], {"haiku-writer": setups.setup(record, "haiku-writer", own, {
            "fakehost": {"tools": {}, **DRIFT}})})
        self.assertEqual((found["prices"], entry["faults"], entry["void_rate"]["with_skill"]["tries"]),
                         (PRICES["date"], None, 3))  # no fault gate here
        self.assertEqual(entry["golden_accuracy"], {"rate": 1.0, "right": 6, "asked": 6})  # q2 and q4 of 3 goldens
        # every run without the skill wrote the wrong poem and said it was done; every run with it was right
        self.assertEqual(entry["false_done"], {
            "with_skill": {"rate": 0.0, "false_done": 0, "decided": 3, "undecided": 0},
            "without_skill": {"rate": 1.0, "false_done": 3, "decided": 3, "undecided": 0}})
        self.assertEqual({arm: (c["runs"], c["money"], c["uncounted"]) for arm, c in entry["cost"].items()},
                         {"with_skill": (3, None, 3), "without_skill": (3, None, 3)})  # the fake host counts none

    def test_the_stop_pair_is_reported_per_arm_and_never_changes_an_outcome(self):
        import stoppair
        self.planned()
        probe, run = self.stored([("with_skill", POND)] * 3 + [("without_skill", HELLO)] * 3)

        def check_then_stop_fails(r):  # every run's stop pair fails, or cannot decide, as a skill's would
            found = gates.check_gate(r)
            for made in r.runs:
                path = Path(made["bundle"]).parent / "checks.json"
                stored = json.loads(path.read_text())
                self.assertEqual([v["check"] for v in stored["reported"]], list(stoppair.CHECKS))
                stored["reported"] = [dict(v, outcome=o) for v, o in zip(stored["reported"], ("fail", "undecidable"))]
                path.write_text(json.dumps(stored))
            return found
        steps = (("probe", probe), ("run", run), ("check", check_then_stop_fails), ("grade", grades.grade_gate),
                 ("label", labels.label_gate))
        declared = {"haiku-writer": {"count.py": {"0": ""}}}
        with mock.patch.object(stoppair, "skill_checks", lambda path=None: declared):
            self.go(steps, grade=done_or_pond)
        [path] = (self.store / "r1" / "labels").iterdir()
        entry = json.loads(path.read_text())["skills"]["haiku-writer"]["fakehost"]
        # the same outcome as with no pair at all (the test above): every run scored, every rate as it was
        self.assertEqual((entry["task_pass_rate"], entry["baseline_pass_rate"], entry["lift"]), (1.0, 0.0, 1.0))
        self.assertEqual(entry["runs"], {"c1, with_skill": 3, "c1, without_skill": 3})
        self.assertFalse([gap for gap in entry["gaps"] if "not scored" in gap or "stop" in gap])
        self.assertEqual(entry["false_done"]["with_skill"]["decided"], 3)
        tally = {"blocked_after_failed_check": {"pass": 0, "fail": 3, "undecidable": 0},
                 "blocked_quotes_output": {"pass": 0, "fail": 0, "undecidable": 3}}
        self.assertEqual(entry["stop_pair"], {"with_skill": tally, "without_skill": tally})

    def test_a_round_with_a_previous_version_compares_the_two_arms_in_its_label(self):
        self.planned()
        probe, run = self.stored([("with_skill", POND)] * 2 + [("with_skill", HELLO)]
                                 + [("previous_version", POND)] * 3 + [("without_skill", HELLO)] * 3)

        def run_previous(r):  # as a plan with `previous` records it
            r.record["previous"] = {"haiku-writer": "0" * 40}
            return run(r)
        steps = (("probe", probe), ("run", run_previous), ("check", gates.check_gate),
                 ("grade", grades.grade_gate), ("label", labels.label_gate))
        with mock.patch.object(labels.verdicts, "missing", lambda found: []), \
                mock.patch.dict(labels.verdicts.THRESHOLDS, {"format_conformance": 1.01}):  # the format count decides
            self.go(steps, grade=done_or_pond)  # (the fixture has no trigger case)
        [path] = (self.store / "r1" / "labels").iterdir()
        entry = json.loads(path.read_text())["skills"]["haiku-writer"]["fakehost"]
        self.assertEqual((entry["task_pass_rate"], entry["previous_pass_rate"]), (0.6667, 1.0))
        self.assertEqual((entry["label"], entry["gaps"]), ("inconclusive", [  # one split case: too close
            "the reference host claude-code was not run", "format conformance 100% below 101% (3 of 3, 0 undecided)",
            "task pass rate too close: 67% as measured, 33% at worst, 100% at best",
            "previous pass rate too close: -33% as measured, -67% at worst, 0% at best",
            "previous false-done rate too close: -33% as measured, -67% at worst, 0% at best"]))
        self.assertEqual(entry["verdicts"]["task pass rate"],
                         {"verdict": "too close", "value": 0.6667, "best": 1.0, "worst": 0.3333,
                          "split": {"with_skill": ["c1"]}})

    def test_a_run_not_scored_and_the_goldens_missed_are_named(self):
        self.planned()
        probe, run = self.stored([("with_skill", POND)])
        steps = (("probe", probe), ("run", run), ("check", gates.check_gate), ("grade", grades.grade_gate),
                 ("label", labels.label_gate))
        self.go(steps, grade=answering(lambda page: "yes"))  # the "no" golden is missed: q2 is untrusted
        [path] = (self.store / "r1" / "labels").iterdir()
        found = json.loads(path.read_text())
        gaps = found["skills"]["haiku-writer"]["fakehost"]["gaps"]
        self.assertIn("c1, with_skill, run 1: not scored (expectation 2 has no trusted answer)", gaps)
        self.assertIn("c1, with_skill: 0 scored run(s), 3 needed", gaps)
        self.assertTrue(any(gap.startswith("haiku-writer/c1 q2: untrusted") for gap in gaps))
        self.assertEqual(found["skills"]["haiku-writer"]["fakehost"]["false_done"], {
            "with_skill": {"rate": None, "false_done": 0, "decided": 0, "undecided": 1}})  # neither is trusted

    def test_a_resume_whose_goldens_pass_still_names_the_doubt_its_kept_grades_carry(self):
        poems = [("with_skill", POND)] * 3 + [("without_skill", HELLO)] * 3

        def label(store, *graders):  # each grader's attempt in turn; the last attempt's label entry
            self.store = self.tmp / store
            self.planned()
            probe, run = self.stored(poems)
            for grade in graders:
                before = set((self.store / "r1" / "labels").glob("*.json"))
                self.go((("probe", probe), ("run", run), ("check", gates.check_gate), ("grade", grades.grade_gate),
                         ("label", labels.label_gate)), grade=grade)
            [path] = set((self.store / "r1" / "labels").glob("*.json")) - before
            return json.loads(path.read_text())["skills"]["haiku-writer"]["fakehost"]

        with mock.patch.object(grades, "REFERENCE", "fakehost"), \
                mock.patch.object(labels.verdicts, "missing", lambda found: []):
            self.assertEqual(label("clean", done_or_pond)["label"], "verified")  # trusted from the start
            entry = label("resumed", self.done_always, done_or_pond)  # q4's golden missed, then passed on the resume
        self.assertEqual(entry["false_done"]["with_skill"]["undecided"], 3)  # its kept answers stay untrusted
        self.assertEqual(entry["label"], "inconclusive")
        self.assertTrue(any(gap.startswith("haiku-writer/c1 q4: untrusted (when graded: ") for gap in entry["gaps"]),
                        entry["gaps"])

    def test_a_question_an_extra_pass_leaves_untrusted_is_named_from_the_pass_s_own_grades(self):
        self.planned()
        probe, run = self.stored([("with_skill", POND)] * 3 + [("without_skill", HELLO)] * 3)

        def extra(r):  # one pass of one run, graded for real by a grader that misses the draft golden on q4
            out, kept = tempfile.mkdtemp(dir=self.tmp), self.store / "r1" / "runs" / "k7" / "bundle"
            record, blobs = goldens.bundle(goldens.Golden("run", wrote(POND)), r.cases[("haiku-writer", "c1")],
                                           r.modules["fakehost"], out, DRIFT, "fakehost 1.0", "named-model",
                                           self.repo / "skills")
            made = {"host": "fakehost", "skill": "haiku-writer", "case": "c1", "arm": "with_skill", "number": 7,
                    "key": "k7", "status": "made"}
            r.runs.append({**made, "bundle": str(evidence.store(record, blobs, kept))})
            checked = [gates.check_one(r, r.runs[-1])]
            r.grade = self.done_always
            graded = grades.grade(r, r.runs[-1:], r.folder / "grades" / r.attempt / "extra-1")
            return {"passes": [{"runs": [made], "checks": checked, "grades": graded["runs"],
                                "goldens": graded["goldens"]}], "skipped": {}}
        steps = (("probe", probe), ("run", run), ("check", gates.check_gate), ("grade", grades.grade_gate),
                 ("extra runs", extra), ("label", labels.label_gate))
        self.go(steps, grade=done_or_pond)
        [path] = (self.store / "r1" / "labels").iterdir()
        pass_folder = self.store / "r1" / "grades" / path.stem
        self.assertEqual(json.loads((pass_folder / "runs" / "k7.json").read_text())["untrusted"],
                         {"q4": "a golden was missed: draft got yes, not no"})  # beside the attempt's other runs
        self.assertEqual({p.relative_to(pass_folder / "extra-1").parts[0]
                          for p in (pass_folder / "extra-1").rglob("*.json")}, {"goldens"})  # the pass's goldens only
        entry = json.loads(path.read_text())["skills"]["haiku-writer"]["fakehost"]
        self.assertEqual(entry["runs"]["c1, with_skill"], 4)  # the extra run is scored: only q4 is untrusted
        self.assertEqual(entry["false_done"]["with_skill"]["undecided"], 1)
        self.assertIn("haiku-writer/c1 q4: untrusted (a golden was missed: draft got yes, not no)", entry["gaps"])

    @staticmethod
    def done_always(adapter, page, asked, model=None, timeout=None, **containment):
        """A stand-in grader that answers yes to q4, the done question, so it misses the draft golden there."""
        graded = done_or_pond(adapter, page, asked)
        return grader.Graded({"answers": [dict(a, answer="yes") if a["id"] == "q4" else a
                                          for a in graded.sheet["answers"]]}, [], [[]])


if __name__ == "__main__":
    unittest.main()
