"""Grading faults: each is caught by the harness's own sheet check, panel, golden gate or view on the repository's
goldens (every place is run in test_faults), and a gate made to miss one is reported as a miss."""

import types
import unittest
from pathlib import PurePosixPath
from unittest import mock

from test_faults import Fake
from test_host import JAIL

import evidence
import faults
import goldens
import grader
import grading
import grading_faults
import teamrelease
import view


def alone(page, asked, graders, tiebreak):
    """A panel that lets its first grader decide every question alone."""
    first = graders[0](page, asked)
    return grader.Panel(dict(first.answers or {}), [], 0, len(asked), [first])


CHECK, GATE, PANEL, TEXT = grading.check, goldens.gate, grader.panel, view.text
FIXED = view.host.FIXED
COVERS, DIFF = evidence.covers, evidence.diff


def unquoted(sheet, ids, page):
    """A sheet check that never looks at what a `no` answer quotes."""
    nos = {n for n, a in enumerate(sheet["answers"], start=1) if isinstance(a, dict) and a.get("answer") == "no"}
    return [p for p in CHECK(sheet, ids, page) if not any(p.startswith(f"answer {n}: the evidence") for n in nos)]


def one_way(case, found, graded):
    """A golden gate that trusts a question asked only one way."""
    return {id_: None if why and "settled yes" in why else why for id_, why in GATE(case, found, graded).items()}


def folded(sheet, ids, page):
    """A sheet check that takes an answer's word in any case."""
    fold = lambda a: {**a, "answer": a["answer"].lower()} if isinstance(a, dict) and isinstance(a.get("answer"), str) \
        else a
    return CHECK({**sheet, "answers": [fold(a) for a in sheet["answers"]]}, ids, page)


def caseless(sheet, ids, page):
    """A sheet check that finds a quote in the page in any case."""
    low = lambda a: {**a, "evidence": a["evidence"].lower()} if isinstance(a, dict) and isinstance(
        a.get("evidence"), str) else a
    return CHECK({**sheet, "answers": [low(a) for a in sheet["answers"]]}, ids, page.lower())


def blind_to_last(case, found, graded):
    """A golden gate that never looks at the last golden's answers: it takes them to be what that golden settles.
    The golden stays in the set, so the gate trusts what the real gate trusts, whatever the goldens sort like."""
    last = found[-1]
    ids = graded[last.name][0]
    return GATE(case, found, {**graded, last.name: (ids, {id_: last.settled[id_] for id_ in ids}, [])})


def unanswered_ok(case, found, graded):
    """A golden gate that does not count a question left unanswered as a miss."""
    return {id_: None if why and "no answer" in why else why for id_, why in GATE(case, found, graded).items()}


def first_on_first(page, asked, graders, tiebreak):
    """A panel that takes the first grader's answer on the first question it is given."""
    found = PANEL(page, asked, graders, tiebreak)
    answers = dict(found.answers)
    if asked and found.graded[0].answers:
        answers[asked[0]["id"]] = found.graded[0].answers[asked[0]["id"]]
    return grader.Panel(answers, found.unanswered, found.agreed, found.asked, found.graded)


def covers_without(clause):
    """`evidence.covers` without one of its clauses: the place itself, or the folders above it."""
    def covers(places, path, before=None, after=None):
        mine = {str(p) for p in PurePosixPath(path).parents}
        holder = before in ("dir", None) and after in ("dir", None)
        return any((clause != "place" and path == place) or place in mine or (
            clause != "above" and holder and path in {str(p) for p in PurePosixPath(place).parents})
            for place in places)
    return covers


def second_alone(page, asked, graders, tiebreak):
    """A panel that lets the second grader decide alone when the first has no sheet."""
    found = PANEL(page, asked, graders, tiebreak)
    if found.graded[0].answers is None and found.graded[1].answers:
        return grader.Panel(dict(found.graded[1].answers), [], 0, found.asked, found.graded)
    return found


def no_fresh(page, asked, graders, tiebreak):
    """A panel that gives an ungraded grader no fresh grader of its host: each grader's first sheet stands."""
    first = [grade_one(page, asked) for grade_one in graders]
    return PANEL(page, asked, [lambda p, a, g=g: g for g in first], tiebreak)


def stand_in_alone(page, asked, graders, tiebreak):
    """A panel that lets a fresh grader standing in for an ungraded one decide every question alone."""
    first = [grade_one(page, asked) for grade_one in graders]
    for number, grade_one in enumerate(graders):
        if first[number].answers is None:
            fresh = grade_one(page, asked)
            if fresh.answers:
                return grader.Panel(dict(fresh.answers), [], 0, len(asked), [first[1 - number], fresh])
    return PANEL(page, asked, [lambda p, a, g=g: g for g in first], tiebreak)


def survivor_wins(page, asked, graders, tiebreak):
    """A panel that, after a stand-in, asks the tie-breaker and then lets the grader that was not replaced decide."""
    found = PANEL(page, asked, graders, tiebreak)
    replaced = [number for number in range(2) if found.graded[number].tries]
    if len(replaced) == 1 and found.graded[replaced[0]].answers:
        kept = found.graded[1 - replaced[0]].answers
        return grader.Panel(dict(kept), [], found.agreed, found.asked, found.graded)
    return found


def team(setup, rng):
    """The pages of the first case with goldens, in order, that is a team install on every golden: its overlay adds a
    release with its manifest and writes the version line into a file of the world. Chosen by that shape, never by
    the seed, so a test that needs it holds however many cases have goldens."""
    for skill, name in grading_faults.held():
        case, found = grading_faults.built(setup, skill, name)
        if found and all(any(PurePosixPath(p).name == teamrelease.SELF for p in r["overlay"].get("release", []))
                         and set(r["overlay"].get("edited") or {}) - {r["overlay"].get("index")}
                         for _, r, _, _ in found):
            return case, found
    raise AssertionError("no case with goldens is a team install")


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
                ("sheet", "not yes or no", mock.patch.object(grading, "check", folded), "did not refuse"),
                ("sheet", "misquoted", mock.patch.object(grading, "check", caseless), "did not refuse"),
                *(("view", place, mock.patch.object(view, "text", lambda value, *args: value[:0]), "own words")
                  for place in ("message", "log", "file")),
                *(("view", place, mock.patch.object(view, "lead_lines", lambda overlay: [overlay["skill"]]),
                   "own words") for place in ("message", "log", "file")),  # it drops every line naming the skill
                *(("view", place, mock.patch.object(view, "text", lambda value, leads, folders: TEXT(
                    value, leads, {})), "the view a grader gets") for place in ("message", "log", "file")),
                *(("view", place, mock.patch.object(view, "lead_lines", lambda overlay: []), "the view a grader gets")
                  for place in ("message", "log", "file")),
                ("view", "log", mock.patch.object(view, "COMMAND_FIELDS", view.COMMAND_FIELDS + (
                    "output", "exit_code")), "the view a grader gets"),
                *(("view", place, mock.patch.object(view, "text", lambda value, leads, folders: TEXT(value, leads, {
                    f"{folder}/": f"{word}/" for folder, word in folders.items()})), "the view a grader gets")
                  for place in ("message", "log", "file")),
                ("view", "log", mock.patch.object(view.host, "FIXED", {**FIXED, "command": str, "action": str}),
                 "the view a grader gets"),
                *(("view", "arm", mock.patch.object(view, "FIELDS", view.FIELDS + (field,)), "the view a grader gets")
                  for field in ("exposure", "requests", "failure", "folders", "host", "model", "transcript")),
                ("sheet", "no quote", mock.patch.object(grading, "check", lambda *a: [
                    p for p in CHECK(*a) if "quotes nothing" not in p]), "did not refuse"),
                ("sheet", "extra field", mock.patch.object(grading, "check", lambda sheet, *a: CHECK(
                    {"answers": sheet["answers"]}, *a)), "did not refuse"),
                ("tie", "one split", mock.patch.object(grader, "panel", first_on_first), "not the split"),
                ("view", "file", mock.patch.object(view.evidence, "covers", lambda places, *a: COVERS(
                    places[:1], *a)), "the view a grader gets"),
                ("view", "file", mock.patch.object(view.evidence, "diff", lambda old, new, places, own: DIFF(
                    old, new, [], own)), "the view a grader gets"),
                ("view", "file", mock.patch.object(view.evidence, "covers", covers_without("above")),
                 "the view a grader gets"),
                ("golden", "one wrong", mock.patch.object(goldens, "gate", blind_to_last), "the plant made wrong"),
                ("golden", "unanswered", mock.patch.object(goldens, "gate", unanswered_ok), "the plant made wrong"),
                ("golden", "all yes", mock.patch.object(goldens, "gate", trusting), "the plant made wrong"),
                ("tie", "one split", mock.patch.object(grader, "panel", alone), "not the split"),
                ("tie", "one ungraded", mock.patch.object(grader, "panel", alone), "decided alone"),
                ("tie", "all split", mock.patch.object(grader, "panel", first_wins), "not the split"),
                ("tie", "one split", mock.patch.object(grader, "panel", first_wins), "not the split"),
                ("tie", "one ungraded", mock.patch.object(grader, "panel", second_alone), "decided alone"),
                ("tie", "one ungraded", mock.patch.object(grader, "panel", no_fresh), "decided alone"),
                ("tie", "one ungraded", mock.patch.object(grader, "panel", stand_in_alone), "decided alone"),
                ("tie", "one ungraded", mock.patch.object(grader, "panel", survivor_wins), "decided alone"),
                ("tie", "one ungraded", mock.patch.object(grader, "panel", first_wins), "decided alone"),
                ("golden", "one-sided", mock.patch.object(goldens, "gate", one_way), "the plant made wrong"),
                ("view", "arm", mock.patch.object(view, "FIELDS", view.FIELDS + ("arm",)), "names"),
                *(("view", place, mock.patch.object(view, "text", lambda value, *args: value), "names")
                  for place in ("message", "log", "file"))):
            for seed in (0, 2, 3, 5):  # at every seed, whatever golden and question it picks
                with self.subTest(fault=fault, place=place, seed=seed), patch:
                    outcome = faults.run(entries[fault], setup, seed=seed, place=place)
                    self.assertFalse(outcome["caught"])
                    self.assertIn(reason, outcome["reason"])

    def test_a_view_that_leaves_a_release_file_of_the_overlay_unguarded_is_a_miss(self):
        setup, entry = self.setup_of(), next(e for e in faults.load() if e["id"] == "view")

        def with_release(setup, rng):  # a team install's overlay: its skill's folder and the release files it adds
            case, found = team(setup, rng)
            for _, record, _, _ in found:
                record["overlay"]["release"] = ["rules/core/work.md"]
            return case, found
        blind = types.SimpleNamespace(**vars(evidence))
        blind.places = lambda overlay: overlay["paths"]  # a view that reads the skill's paths only
        for patch in (mock.patch.object(view, "evidence", blind),  # or one that leaves the first place's folders
                      mock.patch.object(view.evidence, "covers", lambda places, *a: COVERS(places[1:], *a))):
            with self.subTest(patch=patch), mock.patch.object(grading_faults, "_pages", with_release):
                self.assertTrue(faults.run(entry, setup, seed=0, place="file")["caught"])
                with patch:
                    outcome = faults.run(entry, setup, seed=0, place="file")
                self.assertFalse(outcome["caught"])
                self.assertIn("the view a grader gets", outcome["reason"])

    def test_a_view_that_leaves_a_team_profile_s_version_line_is_a_miss(self):
        setup, entry = self.setup_of(), next(e for e in faults.load() if e["id"] == "view")
        with mock.patch.object(grading_faults, "_pages", team):  # a case whose world has a team profile
            self.assertTrue(faults.run(entry, setup, seed=0, place="file")["caught"])
            with mock.patch.object(view.teamrelease, "stated", lambda line: None):
                outcome = faults.run(entry, setup, seed=0, place="file")
        self.assertFalse(outcome["caught"])
        self.assertIn("the view a grader gets", outcome["reason"])

    def test_a_view_whose_covers_misses_a_place_itself_is_a_miss(self):
        setup = self.setup_of()
        entry, pages = next(e for e in faults.load() if e["id"] == "view"), grading_faults._pages

        def with_release(setup, rng):  # a release file's path names no skill, but it is one of the overlay's paths
            case, found = team(setup, rng)
            for _, record, _, _ in found:
                record["overlay"]["release"] = ["rules/core/work.md"]
            return case, found
        for setting in (pages, with_release):  # no name hides a place: only the overlay's own record does
            with self.subTest(setting=setting.__name__), mock.patch.object(grading_faults, "_pages", setting), \
                    mock.patch.object(view.evidence, "covers", covers_without("place")):
                self.assertFalse(faults.run(entry, setup, seed=0, place="file")["caught"])

    def test_a_view_fault_in_a_file_is_caught_on_every_case_with_goldens(self):
        # A file the run wrote can be one the install also edits, such as the index: the plant puts both in it.
        setup, entry = self.setup_of(), next(e for e in faults.load() if e["id"] == "view")
        for skill, name in grading_faults.held():
            pick = lambda setup, rng, skill=skill, name=name: grading_faults.built(setup, skill, name)
            with self.subTest(case=f"{skill}/{name}"), mock.patch.object(grading_faults, "_pages", pick):
                outcome = faults.run(entry, setup, seed=0, place="file")
                self.assertEqual((outcome["caught"], outcome["reason"]), (True, None))

    def test_the_seed_chooses_the_golden_and_the_place(self):
        setup = self.setup_of()
        tie = next(e for e in faults.load() if e["id"] == "tie")
        self.assertEqual({faults.run(tie, setup, seed)["place"] for seed in range(12)},
                         {"one split", "all split", "one ungraded"})
        self.assertEqual(faults.run(tie, setup, 5), faults.run(tie, setup, 5))


if __name__ == "__main__":
    unittest.main()
