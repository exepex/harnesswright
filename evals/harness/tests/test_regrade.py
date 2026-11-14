"""Cross-model grading: every page a round graded, rebuilt from the store and graded again by each route, only under
the round's kit, at its commit, on pages that hash as the round graded them, after every route proved itself."""

import json
import unittest
from unittest import mock

from test_grades import HELLO, POND, Pages, answering, pond
from test_prices import PRICES
from test_runs import DRIFT

import kit
import regrade

ROUTE = ("fakehost", "other-model")
PROVED = {"not run": [], "faults": [{"id": "folder", "place": "writes", "caught": True, "reason": None}]}


class Regrade(Pages):
    def setUp(self):
        super().setUp()
        (self.repo / "evals" / "results").mkdir(parents=True)
        (self.repo / "evals" / "results" / "prices.json").write_text(json.dumps(PRICES))

    def source(self):
        """A round whose one attempt graded two runs and two goldens, its kit approved and its drift kept."""
        self.graded([POND, HELLO], answering(pond))
        kit.approve(self.store, "judge-a", self.repo)
        (self.store / "r1" / "drift").mkdir()
        (self.store / "r1" / "drift" / "fakehost.json").write_text(json.dumps(DRIFT))

    def run_it(self, routes=(ROUTE,), proved=PROVED, calls=None, **options):
        with mock.patch.object(regrade, "prove", lambda *args: proved):
            return regrade.regrade(self.store, "r1", list(routes), repo=self.repo, adapters=self.repo / "adapters",
                                   seed=3, grade=answering(pond, calls), **options)

    def test_each_route_grades_every_page_twice_and_the_round_s_grades_stay(self):
        self.source()
        kept = {p: p.read_text() for p in (self.store / "r1" / "grades").rglob("*.json")}
        calls = []
        out = self.run_it(calls=calls)
        self.assertEqual(calls, [("other-model", ["q2", "q4"])] * 8)  # 2 runs and 2 goldens, two graders each
        pages = json.loads((out / "pages.json").read_text())
        self.assertEqual(sorted((p["kind"], p["host"], p["model"]) for p in pages.values()),
                         [("golden", "fakehost", "named-model")] * 2 + [("run", "fakehost", "named-model")] * 2)
        self.assertEqual(sorted(p["name"] for p in pages.values() if p["kind"] == "golden"),
                         ["golden haiku-writer/c1/no", "golden haiku-writer/c1/yes"])
        route = out / regrade.folder_name(*ROUTE)
        self.assertEqual(json.loads((route / "proved.json").read_text()), PROVED)
        q2 = {}
        for id_, page in pages.items():
            graded = json.loads((route / "pages" / f"{id_}.json").read_text())
            self.assertEqual((graded["page"], graded["questions"], len(graded["graders"])),
                             (page["page"], page["questions"], 2))
            q2[page["name"]] = [[a["answer"] for a in g["sheet"]["answers"] if a["id"] == "q2"]
                                for g in graded["graders"]]
        self.assertEqual(q2, {"k1": [["yes"]] * 2, "k2": [["no"]] * 2, "golden haiku-writer/c1/yes": [["yes"]] * 2,
                              "golden haiku-writer/c1/no": [["no"]] * 2})
        record = json.loads((out / "regrade.json").read_text())
        self.assertEqual((record["seed"], record["prices"], record["routes"]), (3, PRICES["date"], [list(ROUTE)]))
        self.assertEqual({p: p.read_text() for p in (self.store / "r1" / "grades").rglob("*.json")}, kept)

    def test_a_route_that_fails_its_probes_or_faults_stops_the_pass_before_any_grading(self):
        self.source()
        for proved in ({"not run": ["sign-in probe: no"], "faults": []},
                       {"not run": [], "faults": [{"id": "folder", "place": "reads", "caught": False, "reason": "x"}]}):
            calls = []
            with self.subTest(proved=proved), self.assertRaisesRegex(regrade.RegradeError, "fakehost=other-model"):
                self.run_it(proved=proved, calls=calls)
            self.assertEqual(calls, [])

    def test_a_page_that_is_not_the_one_the_round_graded_stops_the_pass(self):
        self.source()
        [record] = (self.store / "r1" / "grades").glob("*/runs/k1.json")
        data = json.loads(record.read_text())
        record.write_text(json.dumps({**data, "page": "0" * 64}))
        with self.assertRaisesRegex(regrade.RegradeError, "k1: the page rebuilt"):
            self.run_it()

    def test_a_changed_kit_case_or_adapter_is_refused(self):
        self.source()
        (self.repo / "evals" / "faults" / "harness.json").write_text('{"faults": [ ]}\n')  # not the approved kit
        with self.assertRaisesRegex(regrade.rounds.RoundError, "evals/faults/harness.json"):
            self.run_it()

    def test_a_round_with_no_graded_attempt_is_refused(self):
        self.planned()
        kit.approve(self.store, "judge-a", self.repo)
        with self.assertRaisesRegex(regrade.RegradeError, "grade gate passed"):
            self.run_it()

    def test_a_route_proves_itself_by_every_probe_and_the_grader_fault_at_each_place(self):
        self.source()
        catalogue = json.loads((regrade.REPO / "evals" / "faults" / "harness.json").read_text())
        (self.repo / "evals" / "faults" / "harness.json").write_text(json.dumps(catalogue))
        record = regrade.gates.read(self.store, "r1", self.repo)
        r = regrade.gates.Round(record, self.store, self.repo, self.repo / "adapters", seed=3)
        module, ran = r.modules["fakehost"], []

        def fault(entry, setup, seed, place):
            ran.append((entry["id"], place, setup.model))
            return {"id": entry["id"], "place": place, "caught": True, "reason": None}
        for passed in (True, False):
            ran.clear()
            found = {"not run": [] if passed else ["sign-in probe: no"], "drift": DRIFT}
            with mock.patch.object(regrade.probes, "probe_host", lambda *a, **k: found), \
                    mock.patch.object(regrade.faults, "run", fault), \
                    mock.patch.object(regrade.rounds, "host_version", lambda *a, **k: {"version": "fakehost 1.0"}):
                proved = regrade.prove(r, module, "other-model", [], 3)
            self.assertEqual(proved["not run"], found["not run"])
            self.assertEqual(ran, [("folder", "writes", "other-model"), ("folder", "reads", "other-model")]
                             if passed else [])  # no fault runs for a route that failed a probe
            self.assertEqual([f["caught"] for f in proved["faults"]], [True, True] if passed else [])

    def test_a_route_is_adapter_and_model(self):
        self.assertEqual(regrade.route("goose=maker/m@up"), ("goose", "maker/m@up"))
        for text in ("goose", "=m", "Goose=m", "a b=m"):
            with self.subTest(text=text), self.assertRaises(regrade.RegradeError):
                regrade.route(text)
        self.assertEqual(regrade.folder_name("goose", "maker/m@up"), "goose_maker_m_up")


if __name__ == "__main__":
    unittest.main()
