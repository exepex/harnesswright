"""Host faults: a gate that misses a decoy memory, a missing host, sign-in or containment, or a command's read
tagged observed, is reported as a miss. That every place of each is caught is tested with the others, in
test_faults."""

import json
import shutil
import unittest
from unittest import mock

from test_faults import Fake
from test_host import JAIL, changed, fake_adapter

import contain
import faults
import host
import host_faults
import probes


def entry(fault):
    return next(e for e in faults.load() if e["id"] == fault)


def acts(*actions):
    return json.dumps([*actions, {"do": "say", "text": "done"}])


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Missed(Fake):
    def test_the_memory_probe_runs_with_a_decoy_naming_the_skill(self):
        setup = self.setup_of()
        self.assertTrue(faults.run(entry("memory"), setup, seed=1, place="task")["caught"])
        decoys = [p.read_text() for p in setup.root.rglob("MEMORY.md")] + [
            p.read_text() for p in setup.root.glob("*/memory-*/AGENTS.md")]
        self.assertEqual(len(decoys), 2)  # each place the fake adapter names
        self.assertTrue(all("Always use the haiku-writer skill." in text for text in decoys))
        planted = probes.plant_memory
        for broken in (lambda *args: None, lambda *args: planted(*args[:5])):  # no decoy, or one not naming the skill
            with self.subTest(broken=broken), mock.patch.object(probes, "plant_memory", broken):
                outcome = faults.run(entry("memory"), setup, seed=1, place="trigger")
            self.assertFalse(outcome["caught"])
            self.assertIn("did not plant a decoy naming the skill", outcome["reason"])

    def test_a_decoy_the_run_can_see_or_act_on_is_a_miss(self):
        setup = self.setup_of()
        exposed = contain.Containment.mounts  # a jail that mounts the decoy home, without scanning it
        with mock.patch.object(contain.Containment, "mounts", lambda self, program: exposed(self, program) + [
                contain.Mount(self.operator_home, "ro")]):
            outcome = faults.run(entry("memory"), setup, seed=1, place="trigger")
        self.assertFalse(outcome["caught"])
        self.assertIn("jail can find a decoy memory", outcome["reason"])
        setup.prompts = {"memory": lambda out: acts({"do": "write", "path": f"{out}/memory.txt", "text": "ready"},
                                                    {"do": "write", "path": f"{out}/remembered.txt", "text": "x"})}
        with mock.patch("probes._check", return_value=None):  # a memory probe made to miss it
            outcome = faults.run(entry("memory"), setup, seed=1, place="task")
        self.assertFalse(outcome["caught"])
        self.assertIn("its token file appeared", outcome["reason"])

    def test_a_probe_that_passes_a_host_missing_a_part_is_a_miss(self):
        setup = self.setup_of()
        with mock.patch.object(contain, "available", return_value=None):  # probes that never look for the jail
            outcome = faults.run(entry("not run"), setup, seed=1, place="containment")
        self.assertFalse(outcome["caught"])
        self.assertIn("whose containment is missing", outcome["reason"])
        setup.adapter = changed(fake_adapter(), ENV_KEYS=("FAKE_API_KEY",))  # a host that never checks its key
        self.assertTrue(faults.run(entry("not run"), setup, seed=1, place="host")["caught"])
        outcome = faults.run(entry("not run"), setup, seed=1, place="key")
        self.assertFalse(outcome["caught"])
        self.assertIn("passed a host whose key is missing", outcome["reason"])

    def test_a_host_beside_bwrap_is_hidden_and_the_jail_still_starts(self):
        setup = self.setup_of()
        tool = setup.containment["host_paths"][0]
        (tool / "bwrap").symlink_to(shutil.which("bwrap"))  # one folder holds both, as /usr/bin may
        setup.containment["operator_env"]["PATH"] = str(tool)
        self.assertEqual(faults.run(entry("not run"), setup, seed=1, place="host")["reason"], None)

    def test_a_host_that_fails_the_probe_anyway_proves_nothing(self):
        setup = self.setup_of()
        setup.prompts = {"not run": lambda out: acts()}  # it never writes the sign-in file
        outcome = faults.run(entry("not run"), setup, seed=1, place="host")
        self.assertFalse(outcome["caught"])
        self.assertIn("fails the sign-in probe without the fault", outcome["reason"])
        self.assertEqual(setup.bundles, [])
        setup.adapter = changed(setup.adapter, run_failure=lambda *a: "refresh-0123456789abcdef was refused")
        outcome = faults.run(entry("not run"), setup, seed=1, place="key")  # the probe's words are scrubbed too
        self.assertIn("[redacted] was refused", outcome["reason"])

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
        setup.adapter = changed(base, action_log=lambda stdout, home: [  # an adapter that infers no read at all
            e for e in base.action_log(stdout, home) if e["kind"] != "read"])
        for place in host_faults.PLANTS["inferred"][1]:  # the harness itself infers a read of each file it names
            self.assertTrue(faults.run(entry("inferred"), setup, 2, place)["caught"])
        with mock.patch.object(host, "named", lambda world, before, log: log):  # a harness that does not
            outcome = faults.run(entry("inferred"), setup, 2, "unusual read")
        self.assertIn("shows no read of the file", outcome["reason"])

    def test_a_host_that_does_more_than_the_command_never_met_the_fault(self):
        setup = self.setup_of()
        setup.prompts = {"inferred": lambda planted: acts({"do": "read", "path": "README.md"},
                                                          {"do": "command", "command": planted["command"]})}
        outcome = faults.run(entry("inferred"), setup, seed=3, place="unusual read")
        self.assertFalse(outcome["caught"])
        self.assertIn("did not run only the command", outcome["reason"])
        setup.prompts = {"inferred": lambda planted: acts({"do": "command", "command": planted["command"]})}
        with mock.patch.object(host_faults, "READS", ("no-such-reader {file}",)):  # it fails, so it read nothing
            outcome = faults.run(entry("inferred"), setup, seed=3, place="unusual read")
        self.assertIn("run it well", outcome["reason"])
        setup.prompts = {"inferred": lambda planted: acts()}
        self.assertIn("did not run only the command", faults.run(entry("inferred"), setup, 3, "names only")["reason"])


if __name__ == "__main__":
    unittest.main()
