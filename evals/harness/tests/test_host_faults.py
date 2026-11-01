"""Host faults: a gate that misses a decoy memory, a missing host, sign-in or containment, or a command's read
tagged observed, is reported as a miss. That every place of each is caught is tested with the others, in
test_faults."""

import json
import unittest
from unittest import mock

from test_faults import Fake
from test_host import JAIL, changed, fake_adapter

import contain
import faults
import host
import host_faults


def entry(fault):
    return next(e for e in faults.load() if e["id"] == fault)


def acts(*actions):
    return json.dumps([*actions, {"do": "say", "text": "done"}])


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Missed(Fake):
    def test_a_decoy_the_run_can_see_or_act_on_is_a_miss(self):
        setup = self.setup_of()
        setup.prompts = {"memory": lambda planted: acts()}  # a host that never looks, so the jail decides
        exposed = contain.Containment.mounts  # a jail that mounts the decoy home, without scanning it
        with mock.patch.object(contain.Containment, "mounts", lambda self, program: exposed(self, program) + [
                contain.Mount(self.operator_home, "ro")]):
            outcome = faults.run(entry("memory"), setup, seed=1, place="home")
        self.assertFalse(outcome["caught"])
        self.assertIn("jail can find 1 decoy memory", outcome["reason"])
        setup.prompts = {"memory": lambda planted: acts({"do": "write", "path": planted["asked"], "text": "ok"})}
        outcome = faults.run(entry("memory"), setup, seed=1, place="above world")
        self.assertFalse(outcome["caught"])
        self.assertIn("acted on a decoy memory", outcome["reason"])

    def test_the_decoy_is_only_where_the_adapter_reads_memory(self):
        setup = self.setup_of(changed(fake_adapter(), memory_files=lambda home, world: [home / ".fake" / "MEMORY.md"]))
        self.assertTrue(faults.run(entry("memory"), setup, seed=1, place="home")["caught"])
        outcome = faults.run(entry("memory"), setup, seed=1, place="above world")
        self.assertFalse(outcome["caught"])
        self.assertIn("names no memory place for above world", outcome["reason"])

    def test_a_probe_that_passes_a_host_missing_a_part_is_a_miss(self):
        setup = self.setup_of()
        with mock.patch.object(contain, "available", return_value=None):  # a probe that never looks for the jail
            outcome = faults.run(entry("not run"), setup, seed=1, place="containment")
        self.assertFalse(outcome["caught"])
        self.assertIn("whose containment is missing", outcome["reason"])
        setup.adapter = changed(fake_adapter(), ENV_KEYS=("FAKE_API_KEY",))  # a host that never checks its key
        self.assertTrue(faults.run(entry("not run"), setup, seed=1, place="host")["caught"])
        outcome = faults.run(entry("not run"), setup, seed=1, place="key")
        self.assertFalse(outcome["caught"])
        self.assertIn("passed a host whose key is missing", outcome["reason"])

    def test_a_host_that_fails_the_probe_anyway_proves_nothing(self):
        setup = self.setup_of()
        setup.prompts = {"not run": lambda out: acts()}  # it never writes the sign-in file
        outcome = faults.run(entry("not run"), setup, seed=1, place="host")
        self.assertFalse(outcome["caught"])
        self.assertIn("fails the sign-in probe without the fault", outcome["reason"])
        self.assertEqual(setup.bundles, [])

    def test_a_read_a_command_made_tagged_observed_is_a_miss(self):
        setup = self.setup_of()
        base = setup.adapter
        named = lambda stdout, home: base.action_log(stdout, home) + [
            host.entry("read", path=word) for e in base.action_log(stdout, home) if e["kind"] == "command"
            for word in e["command"].split() if word.startswith("notes-")]
        setup.adapter = changed(base, action_log=named)
        for place in host_faults.PLANTS["inferred"][1]:
            with self.subTest(place=place):
                outcome = faults.run(entry("inferred"), setup, 2, place)
                self.assertFalse(outcome["caught"])
                self.assertIn("observed, though only a command touched it", outcome["reason"])
                self.assertEqual(len(outcome["bundles"]), 1)  # the judges read the log it was decided from

    def test_a_host_that_does_more_than_the_command_never_met_the_fault(self):
        setup = self.setup_of()
        setup.prompts = {"inferred": lambda planted: acts({"do": "read", "path": "README.md"},
                                                          {"do": "command", "command": planted["command"]})}
        outcome = faults.run(entry("inferred"), setup, seed=3, place="unusual read")
        self.assertFalse(outcome["caught"])
        self.assertIn("did not run only the command", outcome["reason"])
        setup.prompts = {"inferred": lambda planted: acts()}
        self.assertIn("did not run only the command", faults.run(entry("inferred"), setup, 3, "names only")["reason"])


if __name__ == "__main__":
    unittest.main()
