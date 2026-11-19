"""Backstop faults: a without-skill run that copies a passage of the skill is voided by the backstop at the place
it was planted, and a backstop that misses it, or voids the run for another text, is reported as a miss."""

import json
import unittest
from unittest import mock

from test_faults import Fake
from test_host import JAIL
from test_world import AGENTS, INDEX

import backstop
import backstop_faults
import faults
from textruns import words

COPIED = next(e for e in faults.load() if e["id"] == "copied")


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Copied(Fake):
    def test_a_copied_passage_is_voided_at_each_place_it_is_planted(self):
        setup = self.setup_of()
        for place in backstop_faults.PLACES:
            with self.subTest(place=place):
                outcome = faults.run(COPIED, setup, seed=3, place=place)
                self.assertEqual((outcome["caught"], outcome["reason"]), (True, None))
                self.assertEqual(len(outcome["bundles"]), 1)

    def test_a_trigger_case_whose_world_is_read_only_is_planted_in_its_message_only(self):
        setup = self.setup_of(data={"kind": "trigger", "should_trigger": True, "split": "test", "index": INDEX},
                              files={"AGENTS.md": AGENTS})
        outcomes = [faults.run(COPIED, setup, seed) for seed in range(4)]
        self.assertEqual({(o["place"], o["caught"]) for o in outcomes}, {("message", True)})
        with self.assertRaisesRegex(faults.FaultError, "not one of its places"):
            faults.run(COPIED, setup, 1, place="world file")
        view = next(e for e in faults.load() if e["id"] == "view")  # another plant's `file` place is still offered
        self.assertIn("file", {faults.run(view, setup, seed)["place"] for seed in range(16)})

    def test_the_passage_is_the_skill_s_own_text_long_enough_to_void(self):
        setup = self.setup_of()
        seen = []
        setup.prompts = {"copied": lambda planted: seen.append(planted["paragraph"]) or json.dumps(
            [{"do": "say", "text": planted["paragraph"]}])}
        faults.run(COPIED, setup, seed=5, place="message")
        [paragraph] = seen
        self.assertGreaterEqual(len(paragraph.split()), backstop.SPAN)
        self.assertLessEqual(len(paragraph.split()), backstop_faults.LONGEST)
        skill = (self.tmp / "skills" / "haiku-writer" / "SKILL.md").read_text()
        self.assertIn(paragraph, " ".join(words(skill)))  # in the words the backstop compares

    def test_a_backstop_that_misses_the_passage_is_a_miss(self):
        setup = self.setup_of()
        with mock.patch.object(backstop, "check", lambda *args: {"void": [], "short": []}):
            outcome = faults.run(COPIED, setup, seed=3, place="world file")
        self.assertFalse(outcome["caught"])
        self.assertIn("did not void the run", outcome["reason"])

    def test_a_backstop_that_voids_only_for_another_text_is_a_miss(self):
        setup = self.setup_of()
        real = backstop.check

        def blind(record, blob, own, where=None):  # a backstop that never reads changed files
            return real({**record, "diff": {}}, blob, own, where)

        setup.prompts = {"copied": lambda planted: json.dumps([
            {"do": "say", "text": planted["paragraph"]},
            {"do": "write", "path": planted["file"], "text": planted["paragraph"]}])}
        with mock.patch.object(backstop, "check", blind):
            outcome = faults.run(COPIED, setup, seed=3, place="world file")
        self.assertFalse(outcome["caught"])
        self.assertIn("not for the passage at world/", outcome["reason"])

    def test_a_void_for_another_text_is_a_miss(self):
        setup = self.setup_of()
        setup.prompts = {"copied": lambda planted: json.dumps([{"do": "say", "text": planted["paragraph"]}])}
        outcome = faults.run(COPIED, setup, seed=3, place="world file")  # said, never written to the file
        self.assertFalse(outcome["caught"])
        self.assertIn("not for the passage at world/", outcome["reason"])

    def test_a_skill_with_no_passage_long_enough_is_a_miss(self):
        setup = self.setup_of()
        self.skill(text="---\nname: haiku-writer\ndescription: Writes a haiku.\n---\n\n# Haiku writer\n")
        outcome = faults.run(COPIED, setup, seed=3, place="message")
        self.assertFalse(outcome["caught"])
        self.assertIn("no passage of its own long enough", outcome["reason"])


if __name__ == "__main__":
    unittest.main()
