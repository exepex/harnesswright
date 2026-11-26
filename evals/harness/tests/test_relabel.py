"""A relabel grades a labelled round's stored runs again in a copy of the round, making no run."""

import json
import unittest

from test_gates import Gated
from test_runs import DRIFT

from test_grades import POND, wrote

import evidence
import gates
import goldens
import relabel
import rounds
import runs


class Relabel(Gated):
    """A planned round whose one labelled attempt kept one run and voided another."""

    def setUp(self):
        super().setUp()
        self.record = self.planned()
        old = self.store / "r1"
        case = gates.Round(self.record, self.store, self.repo, self.repo / "adapters").cases[("haiku-writer", "c1")]
        record, blobs = goldens.bundle(goldens.Golden("run", wrote(POND)), case, rounds.adapter(
            "fakehost", self.repo / "adapters"), self.tmp / "made", DRIFT, "fakehost 1.0", "m", self.repo / "skills")
        evidence.store(record, blobs, old / "runs" / "k1" / runs.BUNDLE)
        made = [{"key": "k1", "skill": "haiku-writer", "case": "c1", "arm": "with_skill", "number": 1,
                 "host": "fakehost", "status": "kept"}, {"key": "k2", "skill": "haiku-writer", "case": "c1",
                                                          "arm": "without_skill", "number": 1, "host": "fakehost",
                                                          "status": "void"}]
        (old / "runs" / "k1" / "checks.json").write_text("{}")
        for path, data in {"attempts/a.json": {"gates": [{"gate": "run", "passed": True, "outcome": made}]},
                           "labels/a.json": {}, "drift/fakehost.json": DRIFT, "kept-grades/k1.json": {},
                           "grades/a/runs/k1.json": {}}.items():
            (old / path).parent.mkdir(parents=True, exist_ok=True)
            (old / path).write_text(json.dumps(data))
        self.made, self.copy = made, self.tmp / "copy"

    def test_a_copy_holds_the_runs_and_nothing_graded_and_is_made_once(self):
        new = relabel.copy(self.store, "r1", "a", self.copy, self.repo)
        found = sorted(str(p.relative_to(new)) for p in new.rglob("*") if p.is_file())
        self.assertEqual([p for p in found if not p.startswith("runs/k1/bundle/")],
                         ["drift/fakehost.json", "manifest.json", relabel.SOURCE])
        self.assertEqual(json.loads((new / relabel.SOURCE).read_text())["run"], self.made)
        with self.assertRaisesRegex(relabel.RelabelError, "a new folder"):
            relabel.copy(self.store, "r1", "a", self.copy, self.repo)
        (self.store / "r1" / "labels" / "a.json").unlink()
        with self.assertRaisesRegex(relabel.RelabelError, "no labels"):
            relabel.copy(self.store, "r1", "a", self.tmp / "other", self.repo)

    def test_the_run_gate_finds_each_kept_run_and_makes_none(self):
        new = relabel.copy(self.store, "r1", "a", self.copy, self.repo)
        r = gates.Round(self.record, self.copy, self.repo, self.repo / "adapters")
        self.assertEqual(relabel.found_gate(r), self.made)
        self.assertEqual([m["bundle"] for m in r.runs], [str(new / "runs" / "k1" / runs.BUNDLE), None])
        (new / "runs" / "k1" / runs.BUNDLE / "bundle.json").unlink()
        with self.assertRaisesRegex(gates.Stop, "k1: its bundle is not in the store"):
            relabel.found_gate(gates.Round(self.record, self.copy, self.repo, self.repo / "adapters"))

    def test_a_later_commit_is_allowed_only_while_the_round_s_cases_and_skills_are_as_they_were(self):
        relabel.copy(self.store, "r1", "a", self.copy, self.repo)
        steps = (("kit check", relabel.same),)
        (self.repo / "NOTES.md").write_text("later\n")
        self.commit_all()
        with self.assertRaisesRegex(rounds.RoundError, "is not at round r1's commit"):
            gates.run(self.copy, "r1", self.repo, self.repo / "adapters", gates=steps)
        gates.run(self.copy, "r1", self.repo, self.repo / "adapters", gates=steps, at=rounds.commit(self.repo))
        for path, text in (("evals/skills/haiku-writer/cases/c1/case.json", json.dumps({"prompt": "Write two.",
                                                                                         "kind": "task"})),
                           ("skills/haiku-writer/SKILL.md", "changed\n"),
                           ("evals/skills/haiku-writer/cases/c1/world/README.md", "changed\n")):
            (self.repo / path).write_text(text)
            self.commit_all()
            with self.assertRaisesRegex(rounds.RoundError, f"changed since the round's commit .*{path}"):
                gates.run(self.copy, "r1", self.repo, self.repo / "adapters", gates=steps,
                          at=rounds.commit(self.repo))

    def commit_all(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "later")


if __name__ == "__main__":
    unittest.main()
