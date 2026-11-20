"""Grader agreement per question (doc 12, Grader agreement): every answer a grader gave counts, refused tries
included, over runs and goldens alike; the questions below 0.9 or with a flipped retry are named, and nothing is
unscored by agreement."""

import json

from helpers import TempCase

import agreement


def grader_of(*answers, offered=()):
    """A grader entry of a grade record: its accepted sheet's `answers` to q2, and its refused tries' answers."""
    sheet = {"answers": [{"id": "q2", "answer": answers[0], "evidence": "x"}]} if answers else None
    return {"sheet": sheet, "offered": [{"q2": answer} for answer in offered]}


class Questions(TempCase):
    def record(self, path, graders, flipped=(), case="s/c1"):
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"asked": ["q2"], "case": case, "graders": graders, "flipped": list(flipped),
                "answers": {} if flipped else {"q2": "yes"}}
        path.write_text(json.dumps(data))
        return data

    def test_every_answer_counts_refused_tries_and_goldens_too_and_the_named_list_is_one(self):
        runs = self.tmp / "grades" / "a1" / "runs"
        self.record(runs / "k1.json", [grader_of("yes", offered=["no"]), grader_of("yes")])  # its retry disagreed
        self.record(runs / "k2.json", [grader_of("yes"), grader_of("yes")])
        self.record(runs / "k3.json", [grader_of("yes"), grader_of("no"), grader_of("yes")])  # the tie-breaker settled
        self.record(runs / "k4.json", [grader_of("yes", offered=["no"]), grader_of("no")], flipped=["q2"])
        self.record(runs / "k5.json", [grader_of("no"), grader_of("no")], case="s/c2")
        golden = self.tmp / "grades" / "a1" / "goldens" / "s" / "c1" / "yes.json"
        self.record(golden, [grader_of("yes"), grader_of("yes")])
        self.record(self.tmp / "grades" / "a1" / "extra-1" / "goldens" / "s" / "c1" / "yes.json",
                    [grader_of("yes"), grader_of()])  # one answer: says nothing about agreement
        found = agreement.questions(self.tmp, "a1", [{"key": f"k{n}"} for n in range(1, 6)])
        self.assertEqual(found["questions"]["s/c1 q2"], {
            "agreement": {"rate": 0.4, "agreed": 2, "pages": 5}, "flipped": ["k4"]})  # k2 and the golden agree
        self.assertEqual(found["questions"]["s/c2 q2"]["agreement"]["rate"], 1.0)
        self.assertEqual(found["rewrite"], ["s/c1 q2"])
        self.assertEqual((found["threshold"], found["overall"]), (0.9, {"rate": 0.5, "agreed": 3, "pages": 6}))

    def test_a_page_counts_only_when_two_different_graders_answered_it(self):
        runs = self.tmp / "grades" / "a1" / "runs"
        self.record(runs / "k1.json", [grader_of("yes", offered=["yes"]), grader_of()])  # one grader, twice
        self.record(runs / "k2.json", [grader_of(), grader_of("yes", offered=["no"])])  # one grader, two ways
        found = agreement.questions(self.tmp, "a1", [{"key": "k1"}, {"key": "k2"}])
        self.assertEqual(found["questions"]["s/c1 q2"]["agreement"], {"rate": None, "agreed": 0, "pages": 0})
        self.assertEqual(found["overall"], {"rate": None, "agreed": 0, "pages": 0})

    def test_low_agreement_alone_unscores_nothing(self):
        path = self.tmp / "grades" / "a1" / "runs" / "k1.json"
        kept = self.record(path, [grader_of("yes"), grader_of("no"), grader_of("yes")])
        found = agreement.questions(self.tmp, "a1", [{"key": "k1"}])
        self.assertEqual((found["questions"]["s/c1 q2"]["agreement"]["rate"], found["rewrite"]), (0.0, ["s/c1 q2"]))
        self.assertEqual(json.loads(path.read_text()), kept)  # the page's settled answer stands
        self.assertEqual(kept["answers"], {"q2": "yes"})
