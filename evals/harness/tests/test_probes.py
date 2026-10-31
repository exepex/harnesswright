"""Probes: each probe checks the files a host left, through the one run path, and fails a host that did not do it."""

import json
import shlex
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


def loaded(out):
    """The token of the probe world's instructions, as a host that loaded them would have it."""
    return probes.TOKEN.search((Path(out).parent.parent / "world" / "AGENTS.md").read_text()).group()


def q(out, name):
    """A file in the probe-output folder, quoted for the fake host's shell (the tests' folder has a space)."""
    return shlex.quote(f"{out}/{name}")


def command(text):
    return {"do": "command", "command": text}


# For each probe, a fake host that does what the prompt asks, and one that does not.
SOUND = {
    "sign-in": lambda out: acts(command(f"echo ready > {q(out, 'sign-in.txt')}"))(out),
    "powers": lambda out: acts(command(probes.PROMPTS["powers"](out).split("then stop: ")[1]))(out),
    "discovery": lambda out: acts({"do": "skill", "name": probes.SKILL}, command(
        f"grep -o '{TOKEN}' .fake/skills/{probes.SKILL}/SKILL.md > {q(out, 'discovery.txt')}"))(out),
    # The fake host loads no instructions, so the test hands it what a host that loaded them would know.
    "instructions": lambda out: acts(command(f"echo '- {loaded(out)}' > {q(out, 'instructions.txt')}"))(out),
}
UNSOUND = {
    "sign-in": (lambda out: acts({"do": "say", "text": "ready"})(out), "sign-in.txt holds None"),
    "powers": (lambda out: acts(command(f"echo '{{\"write the world\": true}}' > {q(out, 'powers.json')}"))(out),
               "no command that ran the powers probe"),
    "discovery": (lambda out: acts({"do": "say", "text": "Done."})(out), f"no load of {probes.SKILL}"),
    # Every token in the world, the skill's too: not the instructions the host loaded.
    "instructions": (lambda out: acts(command(f"grep -rho '{TOKEN}' . > {q(out, 'instructions.txt')}"))(out),
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
        return probes.probe(adapter or fake_adapter(), name, mode, self.tmp / "pro bes", prompt=prompt, timeout=120,
                            operator_env={"PATH": f"{self.tool}:/usr/bin:/bin", "HTTPS_PROXY": self.upstream.url},
                            operator_home=self.tmp / "operator", host_paths=[self.tool])

    def test_a_host_that_does_what_each_probe_asks_passes_it_in_both_modes(self):
        for name in probes.PROMPTS:
            for mode in ("trigger", "task"):
                with self.subTest(probe=name, mode=mode):
                    self.assertIsNone(self.probe(name, mode, SOUND[name]))
        # Each run had its own fresh world and tokens.
        worlds = sorted(p.parent.name for p in (self.tmp / "pro bes").glob("*/world"))
        self.assertEqual(len(worlds), 2 * len(probes.PROMPTS))

    def test_a_host_that_does_not_fails_the_probe_with_the_reason(self):
        for name, (prompt, reason) in UNSOUND.items():
            with self.subTest(probe=name):
                found = self.probe(name, "trigger", prompt)
                self.assertIn(f"{name} probe, trigger run: ", found)
                self.assertIn(reason, found)
        found = self.probe("discovery", "task", lambda out: acts({"do": "skill", "name": probes.SKILL}, command(
            f"grep -o '{TOKEN}' AGENTS.md > {q(out, 'discovery.txt')}"))(out))  # a token from elsewhere
        self.assertIn("not the token in the probe skill", found)
        tries = sorted(p.name.rsplit("-", 1)[0] for p in (self.tmp / "pro bes").glob("discovery-trigger-*"))
        self.assertEqual(tries, ["discovery-trigger-0", "discovery-trigger-1"])  # asked for twice

    def test_a_probe_needs_the_right_file_and_the_act_in_the_log(self):
        right = {**powers.expected("trigger"), "writable mounts off the table": []}  # the table, written by hand
        for name, prompt, reason in (
                ("sign-in", lambda out: acts(command(f"echo not ready > {q(out, 'sign-in.txt')}"))(out),
                 "sign-in.txt holds 'not ready"),
                ("powers", lambda out: acts(command(f"echo '{json.dumps(right)}' > {q(out, 'powers.json')}"))(out),
                 "no command that ran the powers probe"),
                ("powers", lambda out: acts(command(f"echo '{json.dumps(right)}' > {q(out, 'powers.json')}; "
                                                    "echo powers.py"))(out), "not from this run's probe"),
                ("discovery", lambda out: acts(command(  # read, never loaded as a skill
                    f"grep -o '{TOKEN}' .fake/skills/{probes.SKILL}/SKILL.md > {q(out, 'discovery.txt')}"))(out),
                 f"no load of {probes.SKILL}"),
                ("instructions", lambda out: acts(command(  # read, never loaded as instructions
                    f"grep -o '{TOKEN}' AGENTS.md > {q(out, 'instructions.txt')}"))(out),
                 "read an instruction file")):
            with self.subTest(probe=name, reason=reason):
                self.assertIn(reason, self.probe(name, "trigger", prompt))

    def test_a_skill_the_host_did_not_discover_fails_even_when_the_token_is_found(self):
        lost = fake_adapter()
        lost.skill_dir = lambda world, name: Path(world) / "elsewhere" / name  # not where the host looks
        found = self.probe("discovery", "trigger", lambda out: acts({"do": "say", "text": "searching"}, command(
            f"grep -rho '{TOKEN}' elsewhere > {q(out, 'discovery.txt')}"))(out), lost)
        self.assertIn(f"did not expose {probes.SKILL}", found)

    def test_a_file_the_host_links_elsewhere_is_never_read(self):
        secret = self.tmp / "operator-secret"
        secret.write_text("ready\n")  # outside the jail: a link to it must not pass, nor show what it holds
        found = self.probe("sign-in", "task", lambda out: acts(command(
            f"ln -s {secret} {q(out, 'sign-in.txt')}"))(out))
        self.assertIn("sign-in.txt holds None", found)

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
