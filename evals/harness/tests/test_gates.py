"""The gates of a round: a planned round goes through them in order, the first that fails stops it with its reason,
and every gate's outcome is written to the round's attempt record in the store."""

import json
import shutil
import subprocess
import unittest

from test_gate import Upstream
from test_host import FAKE
from test_runs import DRIFT, JAIL, VERSION, Round

import faults
import gates
import kit
import rounds
from runs import ARMS


class Gated(Round):
    def planned(self, runs_per_arm=2):
        record = self.plan(runs_per_arm)
        rounds.write(record, self.store, self.repo)
        return record

    def go(self, steps, name="r1", **options):
        return gates.run(self.store, name, repo=self.repo, adapters=self.repo / "adapters", gates=steps, seed=7,
                         **options)

    def attempt(self):
        found = sorted((self.store / "r1" / "attempts").glob("*.json"))
        self.assertEqual(len(found), 1)
        return json.loads(found[0].read_text())

    def commit(self):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qam", "next"],
                       cwd=self.repo, check=True, capture_output=True)


class Order(unittest.TestCase):
    def test_every_planned_run_once_with_cases_and_arms_interleaved(self):
        record = {"cases": {"s": {"c1": "", "c2": ""}}, "plan": {"runs": 2}}
        found = list(gates.order(record, ["h"]))
        self.assertEqual(len(found), len(set(found)))
        self.assertEqual(len(found), 8)
        pairs = [found[i:i + 2] for i in range(0, 8, 2)]
        self.assertTrue(all(a[2] == b[2] and a[4] == b[4] and a[3] != b[3] for a, b in pairs))  # one case's two arms
        self.assertEqual([a[3] for a, _ in pairs], [ARMS[0], ARMS[1], ARMS[1], ARMS[0]])  # the first arm alternates
        self.assertEqual([a[2] for a, _ in pairs], ["c1", "c2", "c1", "c2"])


class Gates(Gated):
    def test_the_gates_run_in_order_and_the_first_that_fails_stops_the_round(self):
        self.planned()
        seen = []

        def broken(r):
            raise rounds.RoundError("broken")

        steps = (("a", lambda r: seen.append("a") or {"a": 1}), ("b", broken), ("c", lambda r: seen.append("c")))
        with self.assertRaisesRegex(rounds.RoundError, "stopped at the b gate: broken"):
            self.go(steps)
        self.assertEqual(seen, ["a"])
        attempt = self.attempt()
        self.assertEqual((attempt["round"], attempt["seed"]), ("r1", 7))
        self.assertEqual(attempt["gates"], [{"gate": "a", "passed": True, "outcome": {"a": 1}},
                                            {"gate": "b", "passed": False, "reason": "RoundError: broken"}])

    def test_a_round_that_was_not_planned_or_moved_off_its_commit_is_refused(self):
        with self.assertRaisesRegex(rounds.RoundError, "not a round's name"):
            self.go((), name="../r1")
        with self.assertRaisesRegex(rounds.RoundError, "plan it first"):
            self.go((), name="r2")
        self.planned()
        (self.repo / "evals" / "harness" / "cases.py").write_text("PLAIN = False\n")
        self.commit()
        with self.assertRaisesRegex(rounds.RoundError, "not at round r1's commit"):
            self.go(())

    def test_the_kit_check_refuses_a_kit_the_judges_did_not_approve(self):
        record = self.planned()
        with self.assertRaisesRegex(rounds.RoundError, "stopped at the kit check gate"):
            self.go(gates.GATES[:1])
        catalogue = self.repo / "evals" / "faults" / "harness.json"
        kept = catalogue.read_text()
        catalogue.write_text('{"faults": [1]}\n')
        kit.approve(self.store, "judge-a", self.repo)  # another kit than the round's
        catalogue.write_text(kept)
        with self.assertRaisesRegex(rounds.RoundError, "evals/faults/harness.json"):
            self.go(gates.GATES[:1])
        kit.approve(self.store, "judge-a", self.repo)
        shutil.rmtree(self.store / "r1" / "attempts")
        self.assertEqual(self.go(gates.GATES[:1])["gates"][0]["outcome"], {"approved": record["kit"]})

    def test_lint_passes_a_sound_case_and_stops_a_round_whose_case_is_not(self):
        self.planned()
        self.assertEqual(self.go(gates.GATES[1:2])["gates"][0]["outcome"], {"cases": 1, "hosts": 1})
        self.prompt("Use the haiku-writer skill to write a haiku.")
        self.commit()
        self.planned_again = self.plan()
        shutil.rmtree(self.store)
        rounds.write(self.planned_again, self.store, self.repo)
        with self.assertRaisesRegex(rounds.RoundError, r"stopped at the lint gate: fakehost, haiku-writer/c1: "):
            self.go(gates.GATES[1:2])


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Hosts(Gated):
    def setUp(self):
        super().setUp()
        self.upstream = Upstream()
        self.addCleanup(self.upstream.close)
        self.tool = self.tmp / "tool"
        shutil.copytree(FAKE, self.tool, ignore=shutil.ignore_patterns("adapter.py", "__pycache__"))
        self.options = {"timeout": 120, "operator_home": self.tmp / "operator", "host_paths": [self.tool],
                        "operator_env": {"PATH": f"{self.tool}:/usr/bin:/bin", "HTTPS_PROXY": self.upstream.url}}

    def test_a_round_whose_hosts_all_fail_their_probes_stops(self):
        self.planned()  # the fake host reads no plain prompt, so it fails every probe
        with self.assertRaisesRegex(rounds.RoundError, "stopped at the probe gate: no host passed its probes"):
            self.go(gates.GATES[2:3], **self.options)
        self.assertIn("fakehost", self.attempt()["gates"][0]["reason"])

    def test_the_runs_are_made_interleaved_and_kept_when_the_round_runs_again(self):
        self.planned()

        def probed(r):
            r.hosts["fakehost"] = {"drift": DRIFT, "version": VERSION}

        steps = (("probe", probed), ("run", gates.run_gate))
        made = self.go(steps, **self.options)["gates"][1]["outcome"]
        self.assertEqual([(m["number"], m["arm"]) for m in made],
                         [(1, ARMS[0]), (1, ARMS[1]), (2, ARMS[1]), (2, ARMS[0])])
        self.assertEqual({m["status"] for m in made}, {"made"})
        again = gates.run(self.store, "r1", repo=self.repo, adapters=self.repo / "adapters", gates=steps, seed=8,
                          **self.options)["gates"][1]["outcome"]
        self.assertEqual([m["key"] for m in again], [m["key"] for m in made])
        self.assertEqual({m["status"] for m in again}, {"kept"})

    def test_a_fault_the_harness_misses_stops_the_round(self):
        shutil.copy2(faults.CATALOGUE, self.repo / "evals" / "faults" / "harness.json")
        self.planned()  # the fake host reads none of the catalogue's plain prompts, so a fault that runs it is missed

        def probed(r):
            r.hosts["fakehost"] = {"drift": DRIFT, "version": VERSION}

        with self.assertRaisesRegex(rounds.RoundError, "stopped at the faults gate: faults missed: fakehost, "):
            self.go((("probe", probed), ("faults", gates.faults_gate)), **self.options)
        self.assertFalse(self.attempt()["gates"][1]["passed"])


if __name__ == "__main__":
    unittest.main()
