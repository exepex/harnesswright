"""Cross-model grading: every page a round graded, rebuilt from the store and graded again by each route, only under
the round's kit, at its commit, on pages that hash as the round graded them, after every route proved itself."""

import json
import unittest
from unittest import mock

from test_grades import HELLO, POND, Pages, answering, pond
from test_prices import PRICES
from test_runs import DRIFT

import compare
import gates
import grades
import kit
import regrade

ROUTE = ("fakehost", "other-model")
FAULTS = [{"id": "folder", "place": place, "caught": True, "reason": None} for place in ("writes", "reads")]
PROVED = {"not run": [], "drift": DRIFT, "version": "fakehost 1.0", "faults": FAULTS}


class Regrade(Pages):
    def setUp(self):
        super().setUp()
        (self.repo / "evals" / "results").mkdir(parents=True)
        (self.repo / "evals" / "results" / "prices.json").write_text(json.dumps(PRICES))

    def source(self):
        """A round whose one attempt passed its probes on the fake host and graded two runs and two goldens, its
        kit approved and its drift kept."""
        self.planned()
        steps = (("probe", lambda r: {"passed": ["fakehost"], "not run": {}, "drift": {}}),
                 ("run", self.ran([POND, HELLO])), ("check", gates.check_gate), ("grade", grades.grade_gate))
        self.go(steps, grade=answering(pond))
        kit.approve(self.store, "judge-a", self.repo)
        (self.store / "r1" / "drift").mkdir()
        (self.store / "r1" / "drift" / "fakehost.json").write_text(json.dumps(DRIFT))

    def run_it(self, routes=(ROUTE,), proved=PROVED, calls=None, commit=None, **options):
        record = json.loads((self.store / "r1" / "manifest.json").read_text())
        with mock.patch.object(regrade, "prove", lambda *args: proved), \
                mock.patch.object(regrade.rounds, "commit", lambda repo: commit or record["commit"]):
            return regrade.regrade(self.store, "r1", list(routes), repo=self.repo, adapters=self.repo / "adapters",
                                   seed=3, grade=answering(pond, calls), **options)

    def records(self, kind="runs"):
        return sorted((self.store / "r1" / "grades").glob(f"*/{kind}/**/*.json"))

    def test_each_route_grades_every_page_twice_and_the_round_s_grades_stay(self):
        self.source()
        kept = {p: p.read_text() for p in (self.store / "r1" / "grades").rglob("*.json")}
        calls = []
        out = self.run_it(calls=calls)
        self.assertEqual(calls, [("other-model", ["q2", "q4"])] * 8)  # 2 runs and 2 goldens, two graders each
        pages = json.loads((out / "pages.json").read_text())
        self.assertEqual(sorted(pages), ["0001", "0002", "0003", "0004"])  # named by place in the blind order
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
        self.assertEqual((record["seed"], record["prices"], record["graders"], record["pages"]),
                         (3, PRICES["date"], 2, ["run", "golden"]))
        self.assertEqual([(e["adapter"], e["model"], e["version"], e["upstream"]) for e in record["routes"]],
                         [(*ROUTE, "fakehost 1.0", None)])
        self.assertIsNotNone(record["finished"])  # a pass with no finish time stopped part way
        self.assertEqual({p: p.read_text() for p in (self.store / "r1" / "grades").rglob("*.json")}, kept)

    def test_the_operator_may_grade_one_kind_of_page_with_one_grader(self):
        self.source()
        calls = []
        out = self.run_it(calls=calls, kinds=("golden",), times=1)
        self.assertEqual(calls, [("other-model", ["q2", "q4"])] * 2)
        self.assertEqual({p["kind"] for p in json.loads((out / "pages.json").read_text()).values()}, {"golden"})
        for wrong in ({"kinds": ()}, {"kinds": ("void",)}, {"times": 0}, {"times": 3}, {"routes": ()},
                      {"routes": (ROUTE, ROUTE)}):
            with self.subTest(wrong=wrong), self.assertRaises(regrade.RegradeError):
                self.run_it(**wrong)

    def test_a_route_that_fails_its_probes_or_faults_stops_the_pass_before_any_grading(self):
        self.source()
        for proved in ({**PROVED, "not run": ["sign-in probe: no"], "faults": []},
                       {**PROVED, "faults": [{**FAULTS[1], "caught": False, "reason": "x"}]},
                       {**PROVED, "faults": []}):  # no fault ran: nothing proved
            calls = []
            with self.subTest(proved=proved), self.assertRaisesRegex(regrade.RegradeError, "fakehost=other-model"):
                self.run_it(proved=proved, calls=calls)
            self.assertEqual(calls, [])
        for out in (self.store / "r1" / "regrade").iterdir():
            self.assertIsNone(json.loads((out / "regrade.json").read_text())["finished"])

    def test_a_goldens_only_pass_with_one_grader_is_reported_by_the_comparison_report(self):
        self.source()
        out = self.run_it(kinds=("golden",), times=1)
        found = compare.report(out, repo=self.repo)
        [route] = found["routes"].values()
        self.assertEqual((route["golden accuracy"]["right"], route["golden accuracy"]["asked"]), (4, 4))
        self.assertIsNone(route["graders agree"])
        self.assertEqual((found["pass"]["pages graded"], found["pairs"]), ({"golden": 2}, []))

    def test_a_round_with_an_extra_pass_regrades_its_extra_runs_too(self):
        self.planned()

        def extra(r):  # k2 graded by a pass of the extra runs gate, its goldens mixed in again
            graded = grades.grade(r, r.runs[1:], r.folder / "grades" / r.attempt / "extra-1")
            return {"passes": [{"runs": [{"key": "k2"}], "checks": [], "grades": graded["runs"],
                                "goldens": graded["goldens"]}]}
        steps = (("probe", lambda r: {"passed": ["fakehost"], "not run": {}, "drift": {}}),
                 ("run", lambda r: self.ran([POND, HELLO])(r) or []), ("check", gates.check_gate),
                 ("grade", lambda r: grades.grade(r, r.runs[:1], r.folder / "grades" / r.attempt)),
                 ("extra runs", extra))
        self.go(steps, grade=answering(pond))
        kit.approve(self.store, "judge-a", self.repo)
        (self.store / "r1" / "drift").mkdir()
        (self.store / "r1" / "drift" / "fakehost.json").write_text(json.dumps(DRIFT))
        calls = []
        pages = json.loads((self.run_it(calls=calls) / "pages.json").read_text())
        self.assertEqual(sorted(p["name"] for p in pages.values() if p["kind"] == "run"), ["k1", "k2"])
        self.assertEqual(len(calls), 8)  # both runs and the grade gate's two goldens, two graders each

    def test_a_page_or_questions_that_are_not_the_ones_the_round_graded_stop_the_pass(self):
        self.source()
        for kind, field, name in (("runs", "page", "k1"), ("runs", "questions", "k1"),
                                  ("goldens", "page", "golden haiku-writer/c1/no")):
            [path] = [p for p in self.records(kind) if p.stem == name.rpartition("/")[2]]
            data = path.read_text()
            path.write_text(json.dumps({**json.loads(data), field: "0" * 64}))
            with self.subTest(kind=kind, field=field), \
                    self.assertRaisesRegex(regrade.RegradeError, f"{name}: the page rebuilt"):
                self.run_it()
            path.write_text(data)

    def test_records_from_before_page_hashes_or_not_the_gate_s_pages_are_refused(self):
        self.source()
        [path, other] = self.records()
        data, data_other = json.loads(path.read_text()), other.read_text()
        path.write_text(json.dumps({k: v for k, v in data.items() if k != "page"}))
        with self.assertRaisesRegex(regrade.RegradeError, "graded before grade records kept page hashes"):
            self.run_it()
        path.write_text(json.dumps(data))
        other.unlink()  # a record the grade gate named is missing
        with self.assertRaisesRegex(regrade.RegradeError, "not the runs its grade gate graded"):
            self.run_it()
        other.write_text(data_other)
        golden = [p for p in self.records("goldens") if p.stem == "no"][0]
        kept = golden.read_text()
        golden.unlink()  # a golden the grade gate graded has lost its record
        with self.assertRaisesRegex(regrade.RegradeError, "golden haiku-writer/c1/no: the grade gate graded it"):
            self.run_it()
        golden.write_text(kept)
        (golden.parent / "stray.json").write_text(kept)  # a record of no golden the gate graded
        with self.assertRaisesRegex(regrade.RegradeError, "not the goldens its grade gate graded"):
            self.run_it()

    def test_another_commit_kit_case_or_adapter_is_refused(self):
        self.source()
        with self.assertRaisesRegex(regrade.RegradeError, "commit"):
            self.run_it(commit="f" * 40)
        catalogue = self.repo / "evals" / "faults" / "harness.json"
        approved = catalogue.read_text()
        catalogue.write_text('{"faults": [ ]}\n')  # not the approved kit
        with self.assertRaisesRegex(regrade.RegradeError, "evals/faults/harness.json"):
            self.run_it()
        catalogue.write_text(approved)
        case = self.case_dir / "case.json"
        case.write_text(case.read_text() + "\n")
        with self.assertRaisesRegex(regrade.RegradeError, "changed since the round: haiku-writer/c1"):
            self.run_it()
        case.write_text(case.read_text()[:-1])
        [tracked] = sorted(p for p in (self.repo / "adapters" / "fakehost").rglob("adapter.py"))[:1]
        tracked.write_text(tracked.read_text() + "\n")
        with self.assertRaisesRegex(regrade.RegradeError, "changed since the round: adapter fakehost"):
            self.run_it()

    def test_a_round_with_no_graded_attempt_is_refused(self):
        self.planned()
        kit.approve(self.store, "judge-a", self.repo)
        with self.assertRaisesRegex(regrade.RegradeError, "grade gate passed"):
            self.run_it()

    def test_an_attempt_whose_extra_runs_gate_stopped_part_way_is_no_source(self):
        self.source()
        [path] = (self.store / "r1" / "attempts").glob("*.json")
        attempt = json.loads(path.read_text())
        attempt["gates"].append({"gate": "extra runs", "passed": False, "reason": "RunError: planted"})
        path.write_text(json.dumps(attempt))
        with self.assertRaisesRegex(regrade.RegradeError, f"no attempt {path.stem} whose grade gate passed, and every"):
            regrade.source(regrade.gates.Round(regrade.gates.read(self.store, "r1", self.repo), self.store, self.repo,
                                               self.repo / "adapters"), path.stem)
        with self.assertRaisesRegex(regrade.RegradeError, "whose grade gate passed, and every gate before the label"):
            self.run_it()

    def test_the_latest_source_is_the_last_attempt_to_start(self):
        self.source()
        [path] = (self.store / "r1" / "attempts").glob("*.json")
        path.with_name("99999999T999999-older.json").write_bytes(path.read_bytes())  # as an older store named it
        r = regrade.gates.Round(regrade.gates.read(self.store, "r1", self.repo), self.store, self.repo,
                                self.repo / "adapters")
        self.assertEqual(regrade.source(r)[0], path.stem)
        regrade.endings.claim(path.parent)  # a later attempt killed as it started: an empty record, no source
        self.assertEqual(regrade.source(r)[0], path.stem)

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
            self.assertEqual((proved["not run"], proved["drift"]), (found["not run"], DRIFT))
            self.assertEqual(proved["version"], "fakehost 1.0" if passed else None)
            self.assertEqual(ran, [("folder", "writes", "other-model"), ("folder", "reads", "other-model")]
                             if passed else [])  # no fault runs for a route that failed a probe
            self.assertEqual([f["caught"] for f in proved["faults"]], [True, True] if passed else [])

    def test_a_route_is_adapter_and_model_and_has_its_own_folder(self):
        self.assertEqual(regrade.route("goose=maker/m@up"), ("goose", "maker/m@up"))
        for text in ("goose", "=m", "Goose=m", "a b=m"):
            with self.subTest(text=text), self.assertRaises(regrade.RegradeError):
                regrade.route(text)
        self.assertRegex(regrade.folder_name("goose", "maker/m@up"), r"^goose_maker_m_up-[0-9a-f]{12}$")
        self.assertNotEqual(regrade.folder_name("goose", "a/b"), regrade.folder_name("goose", "a_b"))


if __name__ == "__main__":
    unittest.main()
