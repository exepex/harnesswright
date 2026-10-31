"""Probes against the fake host: a sound host passes every probe in both modes, and each planted fault fails the
probe that must catch it."""

import unittest
from unittest import mock

from helpers import TempCase, needs_jail

import contain
import probes


class ProbeFaults(TempCase):
    def probe(self, adapter=None, mode="task", **env):
        adapter = adapter or self.fake_adapter()
        root = self.tmp / f"probe-{len(list(self.tmp.iterdir()))}"
        report = probes.probe_host(adapter, mode, root, operator_env=self.operator_env(**env),
                                   operator_home=self.tmp / "operator-home", tools=["git"])
        return report, {p["probe"]: p for p in report["probes"]}

    def failed(self, found):
        return {name for name, probe in found.items() if not probe["ok"]}

    @needs_jail
    def test_a_sound_host_passes_every_probe_in_both_modes(self):
        for mode in ("task", "trigger"):
            with self.subTest(mode):
                report, found = self.probe(mode=mode)
                self.assertTrue(report["ok"], [p for p in report["probes"] if not p["ok"]])
                self.assertEqual(set(found), {"sign-in", "memory", "powers", "discovery", "instructions", "tools"})
                self.assertEqual(found["powers"]["detail"]["found"], found["powers"]["detail"]["expected"])

    @needs_jail
    def test_the_tools_probe_sees_tools_installed_beside_the_host(self):
        adapter = self.fake_adapter()
        tool = contain.Path(adapter.CLI).parent / "notes-tool"
        tool.write_text("#!/bin/sh\necho notes-tool 1.2\n")
        tool.chmod(0o755)
        env = self.operator_env(PATH=f"{tool.parent}:/usr/bin:/bin")
        found = probes.tools_probe(adapter, "task", self.tmp / "tools", ["notes-tool"], env)
        self.assertTrue(found["ok"], found["problems"])
        self.assertEqual(found["detail"]["versions"]["notes-tool"], "notes-tool 1.2")

    @needs_jail
    def test_hf02_decoy_memory(self):
        report, found = self.probe()
        self.assertTrue(found["memory"]["ok"])
        # The negative control: a seal that copies the operator's memory into the run's home.
        leaky = self.fake_adapter()
        leaky.CREDENTIAL_FILES = (".claude/CLAUDE.md",)
        report, found = self.probe(leaky)
        self.assertFalse(found["memory"]["ok"])
        self.assertIn("followed a memory", found["memory"]["problems"][0])

    @needs_jail
    def test_hf06_host_shipped_skill(self):
        report, found = self.probe(FAKE_HOST_SKILLS='["skill-creator"]')
        self.assertFalse(report["ok"])
        self.assertTrue(any("undeclared skills: ['skill-creator']" in p for p in found["sign-in"]["problems"]))

    @needs_jail
    def test_hf07_missing_powers_containment_host_or_key(self):
        report, found = self.probe(FAKE_HOST_FAULT="no-commands")
        self.assertFalse(report["ok"])
        self.assertLessEqual({"powers", "discovery", "instructions"}, self.failed(found))

        with mock.patch.object(contain, "available", return_value="bwrap is not installed"):
            report, found = self.probe()
        self.assertEqual(self.failed(found), {"containment"})

        missing = self.fake_adapter()
        missing.CLI = str(self.tmp / "no-such-host")
        report, found = self.probe(missing)
        self.assertIn("missing", found["sign-in"]["problems"][0])

        report, found = self.probe(FAKE_HOST_KEY="")
        self.assertFalse(found["sign-in"]["ok"])
        self.assertEqual(found["memory"]["problems"], ["not measured: sign-in failed"])

    @needs_jail
    def test_a_host_with_more_powers_than_the_table_fails_the_powers_probe(self):
        loose = self.fake_adapter()
        loose.command = lambda mode, world, scratch=None, model=None, deny=(): [loose.CLI, "--write", "/tmp",
                                                                                  "--write", str(world)]
        report, found = self.probe(loose, mode="trigger")
        problems = " ".join(found["powers"]["problems"])
        self.assertFalse(found["powers"]["ok"])
        self.assertIn("write_slash_tmp: allowed", problems)
        # The jail still mounts a trigger world read-only, whatever the host's own sandbox allows.
        self.assertNotIn("write_world", problems)


if __name__ == "__main__":
    unittest.main()
