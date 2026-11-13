"""The gates of a round: a planned round goes through them in order, the first that fails stops it with its reason,
and every gate's outcome is written to the round's attempt record in the store."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from test_gate import Upstream
from test_host import FAKE
from test_runs import DRIFT, JAIL, VERSION, WROTE, Round

import checks
import evidence
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

    def test_what_a_probe_gives_is_kept_only_scrubbed(self):
        self.planned()
        secret, token = "sk-" + "s" * 30, "hw-canary-" + "t" * 20
        run, homes = SimpleNamespace(tokens=[token]), []

        def probe_host(module, root, made, **options):
            made.append(run)
            homes.append(Path(root))  # the probes' homes, which go when the gate is done with them
            return {"not run": [f"sign-in probe: the host said {secret} and {token}"], "drift": None}

        def passed(module, root, made, **options):
            probe_host(module, root, made)
            return {"not run": [], "drift": {"tools": {"go": f"go 1.0 {secret}"}, "own files": {"task": [token]}}}

        def credentials(contained):  # a credential the host refreshed in its home, readable only while it is there
            return [secret] if contained is run and homes[-1].is_dir() else []

        with mock.patch("probes.probe_host", probe_host), \
                mock.patch("scrub.credentials", credentials), \
                self.assertRaises(rounds.RoundError) as stopped:
            self.go(gates.GATES[2:3])
        kept = json.dumps(self.attempt())
        for text in (str(stopped.exception), kept):
            self.assertNotIn(secret, text)
            self.assertNotIn(token, text)
        self.assertIn("sign-in probe: the host said", kept)

        def broken(module, root, made, **options):
            probe_host(module, root, made)
            raise RuntimeError(f"the host broke its contract: {secret}")

        shutil.rmtree(self.store / "r1" / "attempts")
        with mock.patch("probes.probe_host", broken), mock.patch("scrub.credentials", credentials), \
                self.assertRaises(rounds.RoundError) as stopped:
            self.go(gates.GATES[2:3])
        for text in (str(stopped.exception), json.dumps(self.attempt())):
            self.assertNotIn(secret, text)
            self.assertIn("the host broke its contract", text)
        with mock.patch("probes.probe_host", passed), \
                mock.patch("scrub.credentials", credentials):
            kept = json.dumps(self.go(gates.GATES[2:3], version=lambda module, **containment: VERSION))
        pinned = (self.store / "r1" / "drift" / "fakehost.json").read_text()
        for text in (kept, pinned):
            self.assertNotIn(secret, text)
            self.assertNotIn(token, text)
        self.assertIn("go 1.0", pinned)

    def test_a_host_whose_tools_changed_since_the_round_s_drift_record_stops_it(self):
        self.planned()
        measured = iter([{"tools": {"go": "go 1.0"}, "own files": {"task": ["home/a"], "trigger": []}},
                         {"tools": {"go": "go 1.0"}, "own files": {"task": ["home/b"], "trigger": []}},
                         {"tools": {"go": "go 2.0"}, "own files": {"task": ["home/a"], "trigger": []}}])

        def probe_host(module, root, made, **options):
            return {"not run": [], "drift": next(measured)}

        with mock.patch("probes.probe_host", probe_host):
            self.go(gates.GATES[2:3], version=lambda module, **containment: VERSION)
            again = self.go(gates.GATES[2:3], version=lambda module, **containment: VERSION)  # own files differ
            self.assertEqual(again["gates"][0]["outcome"]["passed"], ["fakehost"])
            with self.assertRaisesRegex(rounds.RoundError, "its tools are not the round's"):
                self.go(gates.GATES[2:3], version=lambda module, **containment: VERSION)

    def test_each_attempt_has_its_own_record(self):
        self.planned()
        steps = (("a", lambda r: None),)
        self.go(steps)
        self.go(steps)  # within the same second, by the same process
        self.assertEqual(len(list((self.store / "r1" / "attempts").glob("*.json"))), 2)

    def test_the_command_reports_a_stopped_round_in_one_line(self):
        done = subprocess.run([sys.executable, str(Path(rounds.__file__)), "run", "r9", "--store", str(self.store)],
                              capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(done.returncode, 1)
        self.assertRegex(done.stderr, r"^round: .*round r9 has no manifest; plan it first\n$")

    def test_a_hosts_drift_record_is_the_round_s_once_written(self):
        path = self.tmp / "round" / "drift" / "fakehost.json"
        self.assertEqual(gates._pin(path, DRIFT), DRIFT)
        self.assertEqual(gates._pin(path, {"own files": {"task": ["home/other"], "trigger": []}}), DRIFT)
        self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["fakehost.json"])


JUDGED = {"question": "Is the poem a haiku?", "pass": "Yes when it has three lines.", "fail": "No otherwise.",
          "examples": {"pass": ["Three short lines."], "fail": ["One line."]}}
EXPECTATIONS = [
    {"text": "The poem is written", "source": "format", "judged": JUDGED,
     "check": {"name": "file_state", "args": {"path": "poem.md", "state": "changed"}}},
    {"text": "The poem is a haiku", "source": "format", "judged": JUDGED},
    {"text": "The notes are updated", "source": "format", "judged": JUDGED,
     "check": {"name": "file_state", "args": {"path": "README.md", "state": "changed"}}},
]


def _poem():
    """The record and blobs of a run that wrote poem.md and left README.md as it was."""
    made = checks.Bundle.key({"before": {"README.md": "# Notes app\n"},
                              "after": {"README.md": "# Notes app\n", "poem.md": "An old silent pond\n"}})
    texts = [b"", b"# Notes app\n", b"An old silent pond\n"]
    blobs = {hashlib.sha256(text).hexdigest(): text for text in texts}
    empty = hashlib.sha256(b"").hexdigest()
    return ({"files_after": made.files, "diff": made.changes, "log": [], "final_message": "Done.",
             "transcript": {"stdout": empty, "stderr": empty}}, blobs)


POEM = _poem()
BROKEN = "from checks import Check\n\n\ndef broken(bundle):\n    raise ValueError('planted')\n\n\n" \
         "CHECKS = {'broken': Check(broken, {})}\n"


class Checked(Gated):
    """The check gate, on bundles stored as a run stores them."""

    def setUp(self):
        super().setUp()
        shutil.copytree(checks.LIBRARY, self.repo / "evals" / "checks",
                        ignore=shutil.ignore_patterns("keys", "__pycache__"))
        self.expect(EXPECTATIONS)

    def expect(self, expectations):
        (self.case_dir / "case.json").write_text(json.dumps({"prompt": WROTE, "kind": "task",
                                                             "expectations": expectations}))

    def ran(self, statuses):
        """A run gate that gives one run of each status, each kept or made one with a bundle that wrote poem.md."""
        def step(r):
            for number, status in enumerate(statuses, start=1):
                folder = self.store / "r1" / "runs" / f"k{number}"
                bundle = None  # a void or empty run has no bundle
                if status in ("kept", "made"):
                    bundle = str(evidence.store(*POEM, folder / "bundle"))
                r.runs.append({"key": f"k{number}", "skill": "haiku-writer", "case": "c1", "status": status,
                               "bundle": bundle})
        return step

    def test_each_kept_or_made_run_is_checked_and_its_verdicts_written_beside_its_bundle(self):
        self.planned()
        steps = (("run", self.ran(["made", "void", "kept", "empty"])), ("check", gates.check_gate))
        found = self.go(steps)["gates"][1]["outcome"]
        self.assertEqual([f["key"] for f in found], ["k1", "k3"])  # a void or empty run has nothing to check
        self.assertEqual(found[0], {"key": "k1", "pass": 1, "fail": 1, "undecidable": 0, "asked": ["q2", "q4"]})
        verdicts = json.loads((self.store / "r1" / "runs" / "k1" / "checks.json").read_text())["verdicts"]
        # the done question, last, has no check
        self.assertEqual([v and v["outcome"] for v in verdicts], ["pass", None, "fail", None])
        self.assertEqual(verdicts[2]["check"], "file_state")
        self.assertFalse((self.store / "r1" / "runs" / "k2" / "checks.json").exists())

    def test_a_check_that_breaks_stops_the_round(self):
        (self.repo / "evals" / "checks" / "broken.py").write_text(BROKEN)
        self.expect([{**EXPECTATIONS[0], "check": {"name": "broken", "args": {}}}])
        self.planned()
        with self.assertRaisesRegex(rounds.RoundError, "stopped at the check gate: broken: the check failed to run: "
                                                       "ValueError: planted"):
            self.go((("run", self.ran(["made"])), ("check", gates.check_gate)))
        self.assertEqual(self.attempt()["gates"][1]["reason"],
                         "CheckError: broken: the check failed to run: ValueError: planted")


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Hosts(Gated):
    def setUp(self):
        super().setUp()
        self.upstream = Upstream()
        self.addCleanup(self.upstream.close)
        self.tool = self.tmp / "tool"
        shutil.copytree(FAKE, self.tool, ignore=shutil.ignore_patterns("adapter.py", "__pycache__"))
        self.options = {"timeout": 120, "operator_home": self.tmp / "operator", "host_paths": [self.tool],
                        "operator_env": {"PATH": f"{self.tool}:/usr/bin:/bin", "HTTPS_PROXY": self.upstream.url},
                        "version": lambda module, **containment: VERSION}

    def test_a_round_whose_hosts_all_fail_their_probes_stops(self):
        self.planned()  # the fake host reads no plain prompt, so it fails every probe
        with self.assertRaisesRegex(rounds.RoundError, "stopped at the probe gate: no host passed its probes"):
            self.go(gates.GATES[2:3], **self.options)
        self.assertIn("fakehost", self.attempt()["gates"][0]["outcome"]["not run"])

    def test_the_runs_are_made_interleaved_and_kept_when_the_round_runs_again(self):
        self.planned()

        def probed(r):
            r.hosts["fakehost"] = {"drift": DRIFT}

        steps = (("probe", probed), ("run", gates.run_gate), ("check", gates.check_gate))
        attempt = self.go(steps, **self.options)
        made = attempt["gates"][1]["outcome"]
        self.assertEqual([c["key"] for c in attempt["gates"][2]["outcome"]], [m["key"] for m in made])  # each checked
        self.assertEqual([(m["number"], m["arm"]) for m in made],
                         [(1, ARMS[0]), (1, ARMS[1]), (2, ARMS[1]), (2, ARMS[0])])
        self.assertEqual({m["status"] for m in made}, {"made"})
        again = gates.run(self.store, "r1", repo=self.repo, adapters=self.repo / "adapters", gates=steps, seed=8,
                          **self.options)["gates"][1]["outcome"]
        self.assertEqual([m["key"] for m in again], [m["key"] for m in made])
        self.assertEqual({m["status"] for m in again}, {"kept"})

    def test_the_host_version_is_measured_before_each_run(self):
        self.planned()
        found = iter([VERSION, VERSION, {**VERSION, "version": "fakehost 2.0"}, {**VERSION, "version": "fakehost 2.0"}])

        def probed(r):
            r.hosts["fakehost"] = {"drift": DRIFT}

        def measured(module, **containment):
            return next(found)

        steps = (("probe", probed), ("run", gates.run_gate))
        made = self.go(steps, **{**self.options, "version": measured})["gates"][1]["outcome"]
        self.assertEqual([m["status"] for m in made], ["made", "made", "void", "void"])  # the host changed mid-round

    def test_a_fault_the_harness_misses_stops_the_round(self):
        shutil.copy2(faults.CATALOGUE, self.repo / "evals" / "faults" / "harness.json")
        self.store = self.tmp / ("a-long-store-path-" * 5)  # a jail's socket path must not grow with it
        self.planned()  # the fake host reads none of the catalogue's plain prompts, so a fault that runs it is missed

        def probed(r):
            r.hosts["fakehost"] = {"drift": DRIFT}

        with self.assertRaisesRegex(rounds.RoundError, "stopped at the faults gate: faults missed: fakehost, "):
            self.go((("probe", probed), ("faults", gates.faults_gate)), **self.options)
        stopped = self.attempt()["gates"][1]
        self.assertIn("the host failed", stopped["reason"])
        self.assertNotIn("too long", stopped["reason"])
        found = stopped["outcome"]["fakehost"]  # every fault's outcome is kept, the missed ones too
        self.assertEqual(sorted(f["id"] for f in found), sorted(e["id"] for e in faults.load()))
        self.assertTrue(any(f["caught"] for f in found) and not all(f["caught"] for f in found))


if __name__ == "__main__":
    unittest.main()
