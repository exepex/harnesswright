"""The comparison report of a cross-model grading pass: a route's answer is the one all its graders gave, split and
ungraded are counted apart, and every figure carries its counts."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from helpers import TempCase
from test_prices import PRICES, counts

import compare

A, B = "goose=model-a", "goose=model-b"
SETTLED = {"g-yes": {"q1": "yes", "q2": "yes"}, "g-no": {"q1": "no", "q2": "no"}}
PAGES = {"0001": ("golden", "golden s/c1/g-yes", ["q1", "q2"]), "0002": ("golden", "golden s/c1/g-no", ["q1", "q2"]),
         "0003": ("run", "k1", ["q1"])}
PROVED = {"not run": [], "drift": {}, "version": "goose 1", "faults": [{"id": "folder", "place": "writes",
                                                                    "caught": True, "reason": None}]}
PAID = {"seconds": 1.5, "tokens": {"model-a": counts(1_000_000)}}


def sheet(**answers):
    return {"answers": [{"id": id_, "answer": given, "evidence": "x"} for id_, given in answers.items()]}


def grader(answers, costs=PAID, tries=()):
    return {"sheet": None if answers is None else sheet(**answers), "tries": list(tries), "costs": [costs],
            "logs": [[]]}


GRADED = {  # route: {place: its graders}
    A: {"0001": [grader({"q1": "yes", "q2": "yes"})] * 2,
        "0002": [grader({"q1": "no", "q2": "no"}), grader({"q1": "no", "q2": "yes"})],  # q2 split
        "0003": [grader({"q1": "yes"})] * 2},
    B: {"0001": [grader({"q1": "yes", "q2": "no"})] * 2,  # q2 missed
        "0002": [grader({"q1": "no", "q2": "no"}), grader(None, {"seconds": None, "tokens": None}, ["refused: x"])],
        "0003": [grader({"q1": "no"})] * 2}}


class Report(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "repo"
        (self.repo / "evals" / "results").mkdir(parents=True)
        (self.repo / "evals" / "results" / "prices.json").write_text(json.dumps(PRICES))
        self.out = self.tmp / "pass"
        self.out.mkdir()
        routes = []
        for key, graded in GRADED.items():
            adapter, model = key.split("=")
            routes.append({"adapter": adapter, "model": model, "folder": model, "version": "goose 1", "upstream": None,
                           "adapter_sha256": "a" * 64})
            (self.out / model / "pages").mkdir(parents=True)
            (self.out / model / "proved.json").write_text(json.dumps(PROVED))
            for place, graders in graded.items():
                (self.out / model / "pages" / f"{place}.json").write_text(json.dumps({"graders": graders}))
        self.head = {"round": "r1", "source": "a1", "commit": "c", "kit": "k", "seed": 3, "pages": ["run", "golden"],
                     "graders": 2, "prices": PRICES["date"], "prompt": "p",
                     "finished": "2026-11-14T15:00:00+00:00", "routes": routes}
        self.write_head()
        (self.out / "pages.json").write_text(json.dumps({place: {
            "kind": kind, "name": name, "case": "s/c1", "asked": asked, "host": "claude-code", "model": "m",
            "settled": SETTLED.get(name.rpartition("/")[2])} for place, (kind, name, asked) in PAGES.items()}))

    def write_head(self, **changes):
        (self.out / "regrade.json").write_text(json.dumps({**self.head, **changes}))

    def report(self, family=None):
        return compare.report(self.out, family, repo=self.repo)

    def test_a_route_s_answer_is_the_one_all_its_graders_gave(self):
        both = [grader({"q1": "yes"})] * 2
        self.assertEqual(compare.answer(both, "q1"), "yes")
        self.assertEqual(compare.answer([grader({"q1": "yes"}), grader({"q1": "no"})], "q1"), "split")
        self.assertEqual(compare.answer([grader({"q1": "yes"}), grader(None)], "q1"), "ungraded")
        self.assertEqual(compare.answer(both, "q2"), "ungraded")  # a sheet with no answer to it
        self.assertEqual(compare.answer([grader({"q1": "no"})], "q1"), "no")  # one grader a page

    def test_kappa_is_cohen_s_and_undefined_where_chance_explains_everything(self):
        self.assertEqual(compare.kappa([("yes", "yes"), ("no", "no")]), 1.0)
        self.assertEqual(compare.kappa([("yes", "yes"), ("yes", "no")]), 0.0)
        self.assertEqual(compare.kappa([("yes", "no"), ("no", "yes")]), -1.0)
        self.assertIsNone(compare.kappa([("yes", "yes")] * 3))
        self.assertIsNone(compare.kappa([]))

    def test_each_route_s_accuracy_agreement_untrusted_questions_refusals_and_cost(self):
        found = self.report()
        a, b = found["routes"][A], found["routes"][B]
        self.assertEqual(a["golden accuracy"], {"rate": 0.75, "right": 3, "asked": 4, "split": 1, "ungraded": 0})
        self.assertEqual(b["golden accuracy"], {"rate": 0.25, "right": 1, "asked": 4, "split": 0, "ungraded": 2})
        self.assertEqual(a["graders agree"], {"rate": 0.8, "agreed": 4, "answered": 5})
        self.assertEqual(b["graders agree"], {"rate": 1.0, "agreed": 3, "answered": 3})
        self.assertEqual(sorted(a["untrusted"]), ["s/c1/q2"])  # a split golden answer is a miss
        self.assertEqual(sorted(b["untrusted"]), ["s/c1/q1", "s/c1/q2"])
        self.assertEqual(b["refused"], [{"page": "0002", "grader": 2, "tries": ["refused: x"]}])
        self.assertEqual({k: a["cost"][k] for k in ("tries", "seconds", "money", "uncounted")}, {
            "tries": 6, "seconds": 9.0, "money": 12.0, "uncounted": 0})
        self.assertEqual({k: b["cost"][k] for k in ("tries", "untimed", "money", "uncounted")}, {
            "tries": 6, "untimed": 1, "money": 10.0, "uncounted": 1})
        self.assertEqual((found["pass"]["graders"], found["pass"]["pages graded"]), (2, {"run": 1, "golden": 2}))
        self.assertEqual((a["proved"]["faults"], a["adapter_sha256"]), (PROVED["faults"], "a" * 64))

    def test_every_report_states_the_plan_s_limits_that_hold(self):
        limits = " ".join(self.report()["limits"])
        for words in ("Only the goldens are ground truth", "Host and model are mixed", "No judge approves an adapter",
                      "upstream", "samples are small", "own model family"):
            self.assertIn(words, limits)

    def test_each_pair_s_agreement_kappa_and_disagreements_with_own_family_runs_apart(self):
        [pair] = self.report()["pairs"]
        self.assertEqual(pair["routes"], [A, B])
        self.assertEqual(pair["others"]["agreement"], {
            "golden": {"rate": 0.5, "agreed": 1, "answered": 2, "kappa": 0.0},  # an ungraded answer is not compared
            "run": {"rate": 0.0, "agreed": 0, "answered": 1, "kappa": 0.0}})
        self.assertEqual([(d["page"], d["question"], d[A], d[B], d.get("settled"))
                          for d in pair["others"]["disagreements"]],
                         [("0001", "q2", "yes", "no", "yes"), ("0003", "q1", "yes", "no", None)])
        self.assertEqual(pair["own family"], {"agreement": {}, "disagreements": []})
        [pair] = self.report({A: ["claude-code"]})["pairs"]  # the run is model-a's family's: reported apart, whole
        self.assertEqual(sorted(pair["others"]["agreement"]), ["golden"])
        self.assertEqual(self.report({A: ["claude-code"]})["pass"]["family"], {A: ["claude-code"]})
        self.assertEqual(pair["own family"]["agreement"], {"run": {"rate": 0.0, "agreed": 0, "answered": 1,
                                                                   "kappa": 0.0}})
        self.assertEqual([(d["page"], d["question"]) for d in pair["own family"]["disagreements"]], [("0003", "q1")])

    def test_one_grader_a_page_gives_no_grader_agreement(self):
        self.write_head(graders=1)
        found = self.report()
        self.assertIsNone(found["routes"][A]["graders agree"])
        self.assertEqual(found["pass"]["one grader"], compare.ONE)

    def test_a_pass_that_stopped_or_does_not_match_is_refused(self):
        for changes, words in (({"finished": None}, "no finish time"), ({"prices": "2020-01-01"}, "price file")):
            self.write_head(**changes)
            with self.subTest(words=words), self.assertRaisesRegex(compare.CompareError, words):
                self.report()
        self.write_head()
        with self.assertRaisesRegex(compare.CompareError, "routes the pass did not run"):
            self.report({"goose=other": ["codex"]})
        (self.out / "model-b" / "pages" / "0003.json").unlink()
        with self.assertRaisesRegex(compare.CompareError, "goose=model-b: it did not grade every page"):
            self.report()

    def test_the_command_writes_the_report_beside_the_pass(self):
        with redirect_stdout(io.StringIO()) as said:
            self.assertEqual(compare.main([str(self.out), "--family", "claude-code", A], self.repo), 0)
        written = json.loads((self.out / "report.json").read_text())
        self.assertEqual(len(written["pairs"][0]["own family"]["disagreements"]), 1)
        self.assertIn("goose=model-a: golden accuracy 3/4", said.getvalue())
        prices = self.repo / "evals" / "results" / "prices.json"
        for broken in (lambda: self.write_head(finished=None), lambda: prices.write_text("{}"),
                       lambda: (self.out / "pages.json").unlink()):
            broken()
            with self.subTest(), redirect_stderr(io.StringIO()) as said:
                self.assertEqual(compare.main([str(self.out)], self.repo), 1)  # a line, never a traceback
            self.assertIn("compare: ", said.getvalue())



if __name__ == "__main__":
    unittest.main()
