"""Probes: each probe checks the files a host left, through the one run path, and fails a host that did not do it."""

import json
import os
import re
import shlex
import shutil
import unittest
from unittest import mock
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


def loaded(out, name="AGENTS.md"):
    """The token of a file in the probe world, as a host that loaded it would have it."""
    return probes.TOKEN.search((Path(out).parent.parent / "world" / name).read_text()).group()


def q(out, name):
    """A file in the probe-output folder, quoted for the fake host's shell (the tests' folder has a space)."""
    return shlex.quote(f"{out}/{name}")


def decoy(out):
    """The decoy memory's token, as a host that read a decoy would have it: from the folder above the world."""
    text = (Path(out).parent.parent / "AGENTS.md").read_text()
    return re.search(rf"{contain.TOKEN_PREFIX}-[0-9a-f]{{16}}", text).group()


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
    "memory": lambda out: acts(command(f"echo ready > {q(out, 'memory.txt')}"))(out),
}
UNSOUND = {
    "sign-in": (lambda out: acts({"do": "say", "text": "ready"})(out), "sign-in.txt holds None"),
    "powers": (lambda out: acts(command(f"echo '{{\"write the world\": true}}' > {q(out, 'powers.json')}"))(out),
               "did more than the probe asks"),
    "discovery": (lambda out: acts({"do": "say", "text": "Done."})(out), f"no load of {probes.SKILL}"),
    # A token besides the instructions' one, the skill's: not the instructions the host loaded.
    "instructions": (lambda out: acts(command(
        f"echo '{loaded(out)} {loaded(out, f'.fake/skills/{probes.SKILL}/SKILL.md')}' > "
        f"{q(out, 'instructions.txt')}"))(out),
                     "not the one token of the instruction files"),
    "memory": (lambda out: acts({"do": "say", "text": "ready"})(out), "memory.txt holds None"),
}


class ProbeCase(TempCase):
    """A fake host and an upstream proxy for each test, and the probe run through them."""

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


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Probes(ProbeCase):
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
                 "did more than the probe asks"),
                ("powers", lambda out: acts(command(  # the command as given, with the spec changed first
                    f"echo '{{}}' > {q(out, 'powers-spec.json')}"), command(probes.powers_command(out)))(out),
                 "did more than the probe asks"),
                ("powers", lambda out: acts(command(probes.powers_command(out)), {"do": "write", "path": str(
                    out / "powers.json"), "text": json.dumps(right)})(out), "did more than the probe asks"),
                ("discovery", lambda out: acts(command(  # read, never loaded as a skill
                    f"grep -o '{TOKEN}' .fake/skills/{probes.SKILL}/SKILL.md > {q(out, 'discovery.txt')}"))(out),
                 f"no load of {probes.SKILL}"),
                ("instructions", lambda out: acts(command(  # read, never loaded as instructions
                    f"grep -o '{TOKEN}' AGENTS.md > {q(out, 'instructions.txt')}"))(out),
                 "did more than the probe asks"),
                ("discovery", lambda out: acts({"do": "skill", "name": probes.SKILL}, command(  # more than its token
                    f"grep -ho '{TOKEN}' .fake/skills/{probes.SKILL}/SKILL.md AGENTS.md > "
                    f"{q(out, 'discovery.txt')}"))(out),
                 "not the token in the probe skill"),
                ("instructions", lambda out: acts({"do": "read", "path": "AGENTS.md"}, {  # the host's read tool
                    "do": "write", "path": str(out / "instructions.txt"), "text": loaded(out)})(out),
                 "did more than the probe asks"),
                ("instructions", lambda out: acts(command(  # read through a wildcard, naming no file
                    f"grep -ho '{TOKEN}' ./*.md > {q(out, 'instructions.txt')}"))(out),
                 "did more than the probe asks")):
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


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Memory(ProbeCase):
    def test_a_host_that_acts_on_a_decoy_memory_fails(self):
        for prompt in (lambda out: acts(command(f"echo ready > {q(out, 'memory.txt')}"), command(
                           f"echo {decoy(out)} > {q(out, 'remembered.txt')}"))(out),
                       lambda out: acts(command(f"echo ready > {q(out, 'memory.txt')}"), command(
                           f"echo done > {q(out, 'remembered.txt')}"))(out),  # the decoy's file, without the token
                       lambda out: acts(command(f"echo 'ready' > {q(out, 'memory.txt')}"), {
                           "do": "say", "text": f"I remember {decoy(out)}"})(out)):  # the token in the log
            self.assertIn("acted on a decoy memory", self.probe("memory", "task", prompt))
        # Each run planted a decoy in every place the adapter names, outside the world, in a decoy home.
        for folder in (self.tmp / "pro bes").glob("memory-*"):
            homes = [folder / "operator" / ".fake" / "MEMORY.md", folder / "AGENTS.md"]
            self.assertTrue(all(contain.TOKEN_PREFIX in p.read_text() for p in homes))
            # No file of the operator's but the credential files, and the fake host has none.
            self.assertEqual(sorted(manifest.manifest(folder / "operator")), [".fake", ".fake/MEMORY.md"])

    def test_a_jail_that_can_see_a_memory_place_fails_before_the_host_runs(self):
        leaky = fake_adapter()
        leaky.memory_files = lambda home, world: [self.tool / "MEMORY.md"]  # a place the jail mounts
        self.assertIn(f"the run can see {self.tool / 'MEMORY.md'}", self.probe("memory", "trigger", SOUND["memory"],
                                                                               leaky))
        self.assertEqual(list((self.tmp / "pro bes").glob("memory-trigger-*/run/probe-out/*")), [])  # no host run
        inside = fake_adapter()
        inside.memory_files = lambda home, world: [Path(world) / "MEMORY.md"]
        with self.assertRaisesRegex(ValueError, "inside the world"):
            self.probe("memory", "trigger", SOUND["memory"], inside)

    def test_a_memory_place_the_operator_lets_in_fails_and_an_adapter_must_name_one(self):
        own = self.tmp / "operator" / ".fake"  # the operator's real memory folder, named as a host path
        own.mkdir(parents=True)
        found = probes.probe(fake_adapter(), "memory", "task", self.tmp / "pro bes", prompt=SOUND["memory"],
                             timeout=120, operator_env={"PATH": f"{self.tool}:/usr/bin:/bin",
                                                        "HTTPS_PROXY": self.upstream.url},
                             operator_home=self.tmp / "operator", host_paths=[self.tool, own])
        self.assertIn(f"the run can see {own / 'MEMORY.md'}, where the host reads memory", found)
        real = self.tmp / "real home"  # the operator's real home, beside the one given: its memory counts too
        (real / ".fake").mkdir(parents=True)
        with mock.patch.dict(os.environ, {"HOME": str(real)}):
            found = probes.probe(fake_adapter(), "memory", "task", self.tmp / "pro bes", prompt=SOUND["memory"],
                                 timeout=120, operator_env={"PATH": f"{self.tool}:/usr/bin:/bin",
                                                            "HTTPS_PROXY": self.upstream.url},
                                 operator_home=self.tmp / "operator", host_paths=[self.tool, real / ".fake"])
        self.assertIn(f"the run can see {real / '.fake' / 'MEMORY.md'}", found)
        silent = fake_adapter()
        silent.memory_files = lambda home, world: []
        with self.assertRaisesRegex(ValueError, "names no memory place"):
            self.probe("memory", "trigger", SOUND["memory"], silent)

    def test_a_signed_in_host_passes_and_its_credential_copy_brings_no_decoy(self):
        (self.tmp / "operator" / ".fake").mkdir(parents=True)
        (self.tmp / "operator" / ".fake" / "auth.json").write_text("{}\n")  # beside the decoy MEMORY.md
        signed = fake_adapter()
        signed.CREDENTIAL_FILES = (".fake/auth.json",)
        for mode in probes.MODES:
            self.assertIsNone(self.probe("memory", mode, SOUND["memory"], signed))
        homes = sorted((self.tmp / "pro bes").glob("memory-*/run/home"))
        self.assertTrue(homes and all(sorted(manifest.manifest(h)) == [".fake", ".fake/auth.json", "tmp"]
                                      for h in homes))

    def test_a_credential_file_that_is_a_memory_place_never_carries_memory_in(self):
        (self.tmp / "operator" / ".fake").mkdir(parents=True)
        (self.tmp / "operator" / ".fake" / "MEMORY.md").write_text("the operator's real memory\n")
        both = fake_adapter()
        both.CREDENTIAL_FILES = (".fake/MEMORY.md",)  # the decoy takes its place, so the audit finds its canary
        with self.assertRaisesRegex(contain.ContainmentError, "a canary token is in .*/home/.fake/MEMORY.md"):
            self.probe("memory", "task", SOUND["memory"], both)

    def test_the_decoy_home_holds_only_copies_of_the_credential_files(self):
        operator = self.tmp / "operator"
        (operator / ".fake").mkdir(parents=True)
        (operator / ".fake" / "auth.json").write_text("{}\n")
        (operator / ".fake" / "MEMORY.md").write_text("the operator's own memory\n")
        signed = fake_adapter()
        signed.CREDENTIAL_FILES = (".fake/auth.json",)
        home = probes.decoy_home(signed, self.tmp / "decoy", operator)
        self.assertEqual(sorted(manifest.manifest(home)), [".fake", ".fake/auth.json"])


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Drift(ProbeCase):
    def drift(self, prompt, adapter=None, tools=()):
        return probes.drift(adapter or fake_adapter(), self.tmp / "drift", tools, prompt=prompt, timeout=120,
                            operator_env={"PATH": f"{self.tool}:/usr/bin:/bin", "HTTPS_PROXY": self.upstream.url},
                            operator_home=self.tmp / "operator", host_paths=[self.tool])

    def test_it_records_the_tools_and_the_files_the_host_writes_for_itself(self):
        prompt = acts(command('touch "$HOME/state.json" "$TMPDIR/cache"; echo x >> "$HOME/.fake/auth.json"; '
                              'touch made.txt 2>/dev/null; true'))(None)  # the world only takes it in a task run
        (self.tmp / "operator" / ".fake").mkdir(parents=True)
        (self.tmp / "operator" / ".fake" / "auth.json").write_text("{}\n")
        signed = fake_adapter()
        signed.CREDENTIAL_FILES = (".fake/auth.json",)
        reason, record = self.drift(prompt, signed, tools=["python3", "hw-no-such-tool"])
        self.assertIsNone(reason)
        self.assertEqual(sorted(record["tools"]), ["fakehost", "hw-no-such-tool", "python3"])
        self.assertIsNone(record["tools"]["hw-no-such-tool"])
        self.assertTrue(record["tools"]["python3"]["version"].startswith("Python 3"))
        fake = record["tools"]["fakehost"]
        self.assertEqual((fake["path"], fake["sha256"]), (str(self.tool / "fakehost"), manifest.entry(
            self.tool / "fakehost").split()[1]))
        self.assertEqual(record["own files"], {  # added and changed, in the home, the scratch and the world
            "trigger": ["home/.fake/auth.json", "home/state.json", "home/tmp/cache"],
            "task": ["home/.fake/auth.json", "home/state.json", "scratch/tmp/cache", "world/made.txt"]})

    def test_the_tools_probe_runs_only_in_an_audited_jail(self):
        world = self.tmp / "empty"
        world.mkdir()
        planted = contain.plant_canaries([self.tool])  # a canary the jail can see, through a host path
        run = contain.Containment(fake_adapter(), "trigger", world, {}, root=self.tmp / "run", tokens=planted,
                                  operator_env={"PATH": f"{self.tool}:/usr/bin:/bin"},
                                  operator_home=self.tmp / "operator", host_paths=[self.tool])
        with self.assertRaisesRegex(contain.ContainmentError, "a canary token is in"):
            probes.versions(run, ["python3"])

    def test_a_host_that_fails_its_empty_run_is_not_run(self):
        crashed = fake_adapter()
        crashed.jail_command = lambda mode, world, model: ["fakehost", "--no-such-flag"]
        reason, record = self.drift(acts()(None), crashed)
        self.assertIn("tools and drift probe, trigger run: the host failed: exit code 2", reason)
        self.assertEqual(record["own files"], {})

    def test_probe_host_gives_every_reason_and_the_record(self):
        found = probes.probe_host(fake_adapter(), self.tmp / "all", operator_env={
            "PATH": f"{self.tool}:/usr/bin:/bin", "HTTPS_PROXY": self.upstream.url}, timeout=120,
            operator_home=self.tmp / "operator", host_paths=[self.tool])  # the fake host reads no plain prompt
        self.assertEqual(len(found["not run"]), 2 * len(probes.PROMPTS) + 1)  # one reason a probe and mode, and drift
        self.assertTrue(found["not run"][-1].startswith("tools and drift probe, trigger run: the host failed"))
        self.assertIn("fakehost", found["drift"]["tools"])


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
        with self.assertRaisesRegex(powers.PowersError, "not from this run's probe"):  # another run's output
            powers.check(run, json.dumps({**powers.expected("trigger"), "nonce": "other"}), nonce="mine")
        plain = contain.Containment(fake_adapter(), "trigger", world, manifest.manifest(world), root=self.tmp / "run",
                                    operator_env={"PATH": "/usr/bin:/bin"}, operator_home=self.tmp / "operator")
        self.assertIsNone(plain.probe_out)  # a real run never has the folder

    def test_a_decoy_operator_home_never_opens_the_real_one(self):
        world = self.tmp / "world"
        world.mkdir()
        run = contain.Containment(fake_adapter(), "trigger", world, {}, root=self.tmp / "run",
                                  operator_env={"PATH": "/usr/bin:/bin"}, operator_home=self.tmp / "decoy",
                                  host_paths=[Path(os.path.expanduser("~"))])
        with self.assertRaisesRegex(contain.ContainmentError, "operator's home"):
            run.mounts("fakehost")
        # A host installed in the real home and found on PATH, not named: refused, as in a run with the real home.
        real = self.tmp / "real home"  # the real home is a scratch folder too: no test writes in the operator's
        installed = real / ".local"
        (installed / "bin").mkdir(parents=True)
        shutil.copy(FAKE / "fakehost", installed / "bin" / "fakehost")
        with mock.patch.dict(os.environ, {"HOME": str(real)}):
            run = contain.Containment(fake_adapter(), "trigger", world, {}, root=self.tmp / "run2",
                                      operator_env={"PATH": f"{installed / 'bin'}:/usr/bin:/bin"},
                                      operator_home=self.tmp / "decoy")
            with self.assertRaisesRegex(contain.ContainmentError, "is in the operator's home: name the files"):
                run.mounts("fakehost")


if __name__ == "__main__":
    unittest.main()
