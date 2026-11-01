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
import lint

KEY = "fake-key-0123456789abcdef"
PROMPTS = {
    "outside": lambda planted: json.dumps([
        {"do": "command", "command": "cat " + " ".join(planted["paths"]) + "; ls -a " + " ".join(planted["folders"])},
        {"do": "say", "text": "done"}]),
    "environment": lambda planted: json.dumps([{"do": "command", "command": "env; env > seen.txt"},
                                               {"do": "say", "text": "done"}]),
}


class Catalogue(unittest.TestCase):
    def test_the_catalogue_names_each_plant_once_with_the_fields_it_needs(self):
        entries = faults.load()
        self.assertEqual(sorted(e["id"] for e in entries), sorted(faults.PLANTS))
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


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Planted(TempCase):
    """The fake host in a real jail, with a decoy operator home that holds its credential file."""

    def setup_of(self, adapter=None):
        tool = self.tmp / "tool"
        shutil.copytree(FAKE, tool, ignore=shutil.ignore_patterns("adapter.py", "__pycache__"))
        self.skill()
        operator = self.tmp / "operator" / ".fake"
        operator.mkdir(parents=True)
        (operator / "creds.json").write_text(json.dumps({"refresh": "refresh-0123456789abcdef"}))
        case = self.case({"README.md": "A notes app.\n", "docs/usage.md": "Open the app and write a note.\n"})
        adapter = adapter or changed(fake_adapter(), ENV_KEYS=("FAKE_API_KEY",), CREDENTIAL_FILES=(".fake/creds.json",))
        drift = {"own files": {"task": ["world/.fake-state", "home/.fake/log"], "trigger": ["home/.fake/log"]}}
        return faults.Setup(adapter, case, self.tmp / "skills", self.tmp / "faults", drift, prompts=PROMPTS,
                            operator_env={"PATH": f"{tool}:/usr/bin:/bin", "FAKE_API_KEY": KEY},
                            operator_home=self.tmp / "operator", host_paths=[tool])

    def test_every_place_of_every_fault_is_caught(self):
        setup = self.setup_of()
        for fault in faults.load():
            for place in faults.PLANTS[fault["id"]][1]:
                with self.subTest(fault=fault["id"], place=place):
                    outcome = faults.run(fault, setup, seed=7, place=place)
                    self.assertEqual(outcome, {"id": fault["id"], "place": place, "caught": True, "reason": None})

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
                ("inside", "world", mock.patch.object(contain.Containment, "audit"), "audit passed"),
                ("environment", "operator env", mock.patch.object(contain.Containment, "_environment", passes),
                 "environment holds"),
                ("outside", "beside", mock.patch.object(contain.Containment, "audit", side_effect=OSError("down")),
                 "another outcome: OSError")):
            with self.subTest(fault=fault), patch:
                outcome = faults.run(entries[fault], setup, seed=1, place=place)
                self.assertFalse(outcome["caught"])
                self.assertIn(reason, outcome["reason"])


if __name__ == "__main__":
    unittest.main()
