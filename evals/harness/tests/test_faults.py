"""Harness faults: every fault of the catalogue, planted at every place, is caught by the harness's own gate, and a
gate that misses one is reported as a miss."""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from helpers import TempCase
from test_host import FAKE, JAIL, changed, fake_adapter

import contain
import faults
import host
import lint

KEY = "fake-key-0123456789abcdef"
PROMPTS = {
    "outside": lambda planted: json.dumps([
        {"do": "command", "command": "cat " + " ".join(planted["paths"]) + "; ls -a " + " ".join(planted["folders"])},
        {"do": "say", "text": "done"}]),
    "environment": lambda planted: json.dumps([{"do": "command", "command": "env; env > seen.txt"},
                                               {"do": "say", "text": "done"}]),
    "memory": lambda out: json.dumps([{"do": "write", "path": f"{out}/memory.txt", "text": "ready"},
                                      {"do": "say", "text": "done"}]),
    "not run": lambda out: json.dumps([{"do": "write", "path": f"{out}/sign-in.txt", "text": "ready"},
                                       {"do": "say", "text": "done"}]),
    "inferred": lambda planted: json.dumps([{"do": "command", "command": planted["command"]},
                                            {"do": "say", "text": "done"}]),
}


class Catalogue(unittest.TestCase):
    def test_the_catalogue_names_each_plant_once_with_the_fields_it_needs(self):
        entries = faults.load()
        self.assertEqual(sorted(e["id"] for e in entries), sorted(faults.plants()))
        good = {"faults": entries}
        for broken, reason in (({"faults": entries[1:]}, "not exactly the plants"),
                               ({"faults": [{**entries[0], "extra": 1}] + entries[1:]}, "not allowed"),
                               ({"faults": [{"id": "outside", "row": "x"}] + entries[1:]}, "needs a prompt"),
                               ({"faults": [{**entries[0], "row": 3}] + entries[1:]}, "not of their shape"),
                               ({"faults": "outside"}, "not an object"), ({}, "not a fault catalogue")):
            with self.subTest(reason=reason), self.assertRaisesRegex(faults.FaultError, reason):
                faults.load(self.path(broken))
        self.assertEqual(faults.load(self.path(good)), entries)

    def path(self, data):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        self.addCleanup(os.unlink, handle.name)
        with handle:
            json.dump(data, handle)
        return handle.name


class Fake(TempCase):
    """The fake host in a real jail, signing in with a key or a credential file in a decoy operator home."""

    def setup_of(self, adapter=None, data=None):
        tool = self.tmp / "tool"
        shutil.copytree(FAKE, tool, ignore=shutil.ignore_patterns("adapter.py", "__pycache__"))
        self.skill()
        operator = self.tmp / "operator" / ".fake"
        operator.mkdir(parents=True)
        (operator / "creds.json").write_text(json.dumps({"refresh": "refresh-0123456789abcdef"}))
        case = self.case({"README.md": "A notes app.\n", "docs/usage.md": "Open the app and write a note.\n"}, data)
        base = fake_adapter()
        adapter = adapter or changed(base, ENV_KEYS=("FAKE_API_KEY",), CREDENTIAL_FILES=(".fake/creds.json",),
                                     jail_command=lambda *args: base.jail_command(*args) + ["--sign-in"])
        drift = {"own files": {"task": ["world/.fake-state", "home/.fake/log"], "trigger": ["home/.fake/log"]}}
        return faults.Setup(adapter, case, self.tmp / "skills", self.tmp / "faults", drift, prompts=PROMPTS,
                            operator_env={"PATH": f"{tool}:/usr/bin:/bin", "FAKE_API_KEY": KEY},
                            operator_home=self.tmp / "operator", host_paths=[tool])


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Planted(Fake):
    def test_every_place_of_every_fault_is_caught(self):
        setup = self.setup_of()
        for fault in faults.load():
            for place in faults.plants()[fault["id"]][1]:
                with self.subTest(fault=fault["id"], place=place):
                    outcome = faults.run(fault, setup, seed=7, place=place)
                    bundles = outcome.pop("bundles")
                    self.assertEqual(outcome, {"id": fault["id"], "place": place, "caught": True, "reason": None})
                    self.assertEqual(len(bundles), 1 if faults.plants()[fault["id"]][2] else 0)
        self.assertEqual(sorted(p.name for p in faults.REPO.glob(".hw-fault-*")), [])  # the plant is removed

    def test_the_seed_chooses_the_place_and_a_place_must_be_the_plant_s(self):
        setup = self.setup_of(fake_adapter())  # no credential file, so it has no credential place
        inside = next(e for e in faults.load() if e["id"] == "inside")
        chosen = {faults.run(inside, setup, seed)["place"] for seed in range(12)}
        self.assertEqual(chosen, {"world", "host path"})
        self.assertEqual(faults.run(inside, setup, 3)["place"], faults.run(inside, setup, 3)["place"])
        with self.assertRaisesRegex(faults.FaultError, "not one of its places"):
            faults.run(inside, setup, 3, place="credential")

    def test_a_gate_that_misses_a_fault_is_a_miss(self):
        setup = self.setup_of()
        entries = {e["id"]: e for e in faults.load()}
        built = contain.Containment._environment
        passes = lambda self: {**built(self), **{k: v for k, v in self.operator_env.items() if k.isupper()}}
        for fault, place, patch, reason in (
                ("names", "prompt/name", mock.patch.object(lint, "lint", return_value=[]), "did not refuse"),
                ("tells", "file/eval file", mock.patch.object(lint, "RULES", {**lint.RULES, "world": ("tells",)}),
                 "as 'holds eval text'"),
                ("inside", "world", mock.patch.object(contain.Containment, "audit"), "audit passed"),
                ("environment", "operator env", mock.patch.object(contain.Containment, "_environment", passes),
                 "environment holds"),
                ("outside", "beside", mock.patch.object(contain.Containment, "audit", side_effect=OSError("down")),
                 "another outcome: OSError"),
                ("environment", "operator env", mock.patch.object(host, "run", return_value=host.Result(
                    "", "", 1, False, f"turn failed: bad key {KEY}", [], None, [], 0.0)), "never met"),
                ("outside", "machine", mock.patch.object(host, "run", side_effect=host.HostError(f"read {KEY}")),
                 "HostError"),
                ("environment", "operator env", mock.patch("scrub.Scrub.text", lambda self, value, *a, **k: value),
                 "reached the bundle"),
                ("environment", "operator env", mock.patch("scrub.credentials", return_value=[]), "reached the bundle")):
            with self.subTest(fault=fault), patch:
                outcome = faults.run(entries[fault], setup, seed=1, place=place)
                self.assertFalse(outcome["caught"])
                self.assertIn(reason, outcome["reason"])
                self.assertNotIn(KEY, outcome["reason"])  # a failure's words are the run's, and scrubbed


    def test_the_jail_not_the_host_decides_outside_and_a_base_url_is_no_secret(self):
        adapter = changed(fake_adapter(), ENV_KEYS=("FAKE_API_KEY", "FAKE_BASE_URL"))
        setup = self.setup_of(adapter)
        setup.containment["operator_env"]["FAKE_BASE_URL"] = "https://gateway.example.test/v1"
        entries = {e["id"]: e for e in faults.load()}
        self.assertTrue(faults.run(entries["environment"], setup, seed=2)["caught"])  # printed whole, and fine
        os.mkfifo(self.tmp / "skills" / "haiku-writer" / "pipe")  # untracked, so never part of the skill's copy
        silent = lambda planted: json.dumps([{"do": "say", "text": "I will not look."}])
        setup.prompts = {"outside": silent, "environment": silent}
        self.assertTrue(faults.run(entries["outside"], setup, seed=2, place="beside")["caught"])
        with mock.patch("scrub.Scrub.text", lambda self, value, *a, **k: value):  # the harness's own dump shows it
            self.assertFalse(faults.run(entries["environment"], setup, seed=2)["caught"])
        exposed = contain.Containment.mounts  # a jail that mounts the planted folder, without scanning it
        with mock.patch.object(contain.Containment, "mounts", lambda self, program: exposed(self, program) + [
                contain.Mount(self.root.parent, "ro")]):
            outcome = faults.run(entries["outside"], setup, seed=2, place="beside")  # the host still never looks
        self.assertFalse(outcome["caught"])
        self.assertIn("jail can find", outcome["reason"])

    def test_a_sibling_the_without_skill_arm_installs_may_be_exposed(self):
        self.skill("note-taker")
        setup = self.setup_of(data={"siblings": ["note-taker"]})
        environment = next(e for e in faults.load() if e["id"] == "environment")
        self.assertTrue(faults.run(environment, setup, seed=4)["caught"])

    def test_a_credential_file_that_is_a_link_is_never_followed(self):
        setup = self.setup_of()
        real = self.tmp / "real-creds.json"
        real.write_text("{}\n")
        link = self.tmp / "operator" / ".fake" / "creds.json"
        link.unlink()
        link.symlink_to(real)
        inside = next(e for e in faults.load() if e["id"] == "inside")
        outcome = faults.run(inside, setup, seed=1, place="credential")
        self.assertFalse(outcome["caught"])
        self.assertIn("without following a link", outcome["reason"])
        self.assertEqual(real.read_text(), "{}\n")


if __name__ == "__main__":
    unittest.main()
