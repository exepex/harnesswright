"""Probes: each probe checks the files a host left, through the one run path, and fails a host that did not do it."""

import json
import shutil
import unittest
from pathlib import Path

from helpers import TempCase
from test_gate import Upstream
from test_host import FAKE, fake_adapter

import contain
import manifest
import powers
import probes

JAIL = contain.available()
TOKEN = f"{probes.TOKEN_PREFIX}-[0-9a-f]*"


def acts(*actions):
    """A fake host prompt: the actions, as the fake host reads them."""
    return lambda out: json.dumps(list(actions))


def command(text):
    return {"do": "command", "command": text}


# For each probe, a fake host that does what the prompt asks, and one that does not.
SOUND = {
    "sign-in": lambda out: acts(command(f"echo ready > {out}/sign-in.txt"))(out),
    "powers": lambda out: acts(command(f"{contain.PYTHON} -I {out}/powers.py < {out}/powers-spec.json "
                                       f"> {out}/powers.json"))(out),
    "discovery": lambda out: acts({"do": "skill", "name": probes.SKILL}, command(
        f"grep -o '{TOKEN}' .fake/skills/{probes.SKILL}/SKILL.md > {out}/discovery.txt"))(out),
    "instructions": lambda out: acts(command(f"grep -o '{TOKEN}' AGENTS.md > {out}/instructions.txt"))(out),
}
UNSOUND = {
    "sign-in": (lambda out: acts({"do": "say", "text": "ready"})(out), "sign-in.txt holds None"),
    "powers": (lambda out: acts(command(f"echo '{{\"write the world\": true}}' > {out}/powers.json"))(out),
               "read the world: does not work, the table says it must"),
    "discovery": (lambda out: acts({"do": "say", "text": "Done."})(out), "discovery.txt holds None"),
    # Every token in the world, the skill's too: not the instructions the host loaded.
    "instructions": (lambda out: acts(command(f"grep -rho '{TOKEN}' . > {out}/instructions.txt"))(out),
                     "not the one token of the instruction files"),
}


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Probes(TempCase):
    def setUp(self):
        super().setUp()
        self.upstream = Upstream()
        self.addCleanup(self.upstream.close)
        self.tool = self.tmp / "tool"
        shutil.copytree(FAKE, self.tool, ignore=shutil.ignore_patterns("adapter.py", "__pycache__"))

    def probe(self, name, mode, prompt, adapter=None):
        return probes.probe(adapter or fake_adapter(), name, mode, self.tmp / "probes", prompt=prompt, timeout=120,
                            operator_env={"PATH": f"{self.tool}:/usr/bin:/bin", "HTTPS_PROXY": self.upstream.url},
                            operator_home=self.tmp / "operator", host_paths=[self.tool])

    def test_a_host_that_does_what_each_probe_asks_passes_it_in_both_modes(self):
        for name in probes.PROMPTS:
            for mode in ("trigger", "task"):
                with self.subTest(probe=name, mode=mode):
                    self.assertIsNone(self.probe(name, mode, SOUND[name]))
        # Each run had its own fresh world and tokens.
        worlds = sorted(p.parent.name for p in (self.tmp / "probes").glob("*/world"))
        self.assertEqual(len(worlds), 2 * len(probes.PROMPTS))

    def test_a_host_that_does_not_fails_the_probe_with_the_reason(self):
        for name, (prompt, reason) in UNSOUND.items():
            with self.subTest(probe=name):
                found = self.probe(name, "trigger", prompt)
                self.assertIn(f"{name} probe, trigger run: ", found)
                self.assertIn(reason, found)
        found = self.probe("discovery", "task", lambda out: acts(command(  # a token from elsewhere
            f"grep -o '{TOKEN}' AGENTS.md > {out}/discovery.txt"))(out))
        self.assertIn("not the token in the probe skill", found)
        tries = sorted(p.name for p in (self.tmp / "probes").glob("discovery-trigger-*"))
        self.assertEqual(tries, ["discovery-trigger-0", "discovery-trigger-1"])  # asked for twice

    def test_a_host_that_crashes_fails_the_probe(self):
        crashed = fake_adapter()
        crashed.jail_command = lambda mode, world, model: ["fakehost", "--no-such-flag"]
        self.assertIn("the host failed: exit code 2", self.probe("sign-in", "task", SOUND["sign-in"], crashed))


class Folder(TempCase):
    def test_only_a_probe_run_has_the_probe_output_folder_and_the_powers_probe_allows_it(self):
        world = self.tmp / "world"
        world.mkdir()
        (world / "README.md").write_text("A notes app.\n")
        for probe in (False, True):
            run = contain.Containment(fake_adapter(), "trigger", world, manifest.manifest(world),
                                      root=self.tmp / f"run-{probe}", operator_env={"PATH": "/usr/bin:/bin"},
                                      operator_home=self.tmp / "operator", probe=probe)
            out = [m for m in run.mounts("fakehost") if m.path == str(self.tmp / f"run-{probe}" / "probe-out")]
            self.assertEqual([(m.how, m.scan) for m in out], [("rw", True)] if probe else [])
            self.assertEqual(str(run.probe_out) in powers.spec(run)["writable"], probe)
        run.put_probe("powers.py", "print(1)\n")
        self.assertEqual(run.probe_entries, manifest.manifest(Path(run.probe_out)))


if __name__ == "__main__":
    unittest.main()
