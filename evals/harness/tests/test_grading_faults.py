"""Grading faults: each is caught by the harness's own sheet check, panel, golden gate or view on the repository's
goldens (every place is run in test_faults), and a gate made to miss one is reported as a miss."""

import unittest
from unittest import mock

from test_faults import Fake
from test_host import JAIL

import faults
import goldens
import grader
import grading
import view
import world


def alone(page, asked, graders, tiebreak):
    """A panel that lets its first grader decide every question alone."""
    first = graders[0](page, asked)
    return grader.Panel(dict(first.answers or {}), [], 0, len(asked), [first])


CHECK, GATE, PANEL, NAMES = grading.check, goldens.gate, grader.panel, world.names


def unquoted(sheet, ids, page):
    """A sheet check that never looks at what a `no` answer quotes."""
    nos = {n for n, a in enumerate(sheet["answers"], start=1) if isinstance(a, dict) and a.get("answer") == "no"}
    return [p for p in CHECK(sheet, ids, page) if not any(p.startswith(f"answer {n}: the evidence") for n in nos)]


def one_way(case, found, graded):
    """A golden gate that trusts a question asked only one way."""
    return {id_: None if why and "settled yes" in why else why for id_, why in GATE(case, found, graded).items()}


def first_wins(page, asked, graders, tiebreak):
    """A panel that asks the tie-breaker, then keeps the first grader's answers."""
    found = PANEL(page, asked, graders, tiebreak)
    return grader.Panel(dict(found.graded[0].answers), [], found.agreed, found.asked, found.graded)


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Missed(Fake):
    def test_a_gate_that_misses_a_grading_fault_is_a_miss(self):
        setup = self.setup_of()
        entries = {e["id"]: e for e in faults.load()}
        trusting = lambda case, found, graded: {f"q{n}": None for n in range(1, len(case.expectations) + 1)}
        for fault, place, patch, reason in (
                ("sheet", "twice", mock.patch.object(grading, "check", return_value=[]), "did not refuse"),
                ("sheet", "misquoted", mock.patch.object(grading, "check", unquoted), "did not refuse"),
                ("golden", "all yes", mock.patch.object(goldens, "gate", trusting), "the plant made wrong"),
                ("tie", "one split", mock.patch.object(grader, "panel", alone), "not the split"),
                ("tie", "one ungraded", mock.patch.object(grader, "panel", alone), "decided alone"),
                ("tie", "all split", mock.patch.object(grader, "panel", first_wins), "not the split"),
                ("golden", "one-sided", mock.patch.object(goldens, "gate", one_way), "the plant made wrong"),
                ("view", "arm", mock.patch.object(view, "FIELDS", view.FIELDS + ("arm",)), "names"),
                ("view", "message", mock.patch.object(view.world, "names", lambda n: NAMES(n[1:])), "names"),
                ("view", "command", mock.patch.multiple(view, on_overlay=lambda *a: False, text=lambda v, *a: v),
                 "names"),
                ("view", "message", mock.patch.object(view, "text", lambda value, *args: value), "names")):
            with self.subTest(fault=fault, place=place), patch:
                outcome = faults.run(entries[fault], setup, seed=3, place=place)
                self.assertFalse(outcome["caught"])
                self.assertIn(reason, outcome["reason"])

    def test_the_seed_chooses_the_golden_and_the_place(self):
        setup = self.setup_of()
        tie = next(e for e in faults.load() if e["id"] == "tie")
        self.assertEqual({faults.run(tie, setup, seed)["place"] for seed in range(12)},
                         {"one split", "all split", "one ungraded"})
        self.assertEqual(faults.run(tie, setup, 5), faults.run(tie, setup, 5))


if __name__ == "__main__":
    unittest.main()
