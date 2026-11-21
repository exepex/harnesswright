"""The rule of `tells`: an arm word may be only in a world file that both arms are built holding byte for byte and
the run left as built; anywhere else it counts, and the skill's names count everywhere."""

import copy
import hashlib
import random
import unittest
from unittest import mock

from test_faults import Fake
from test_host import JAIL

import evidence
import grading_faults
import tells
import view

ARM_TEXT = b"Runs go in two arms, with_skill and without_skill, and previous_version.\n"


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Tells(Fake):
    def page(self):
        setup = self.setup_of()
        case, pages = grading_faults._pages(setup, random.Random(0))
        _, record, blob, _ = pages[0]
        names = [record["overlay"]["skill"], *evidence.places(record["overlay"])]
        return setup, case, record, blob, names

    def test_an_arm_word_counts_unless_both_arms_are_built_holding_its_file_unchanged(self):
        setup, case, record, blob, names = self.page()
        held = tells.shared(tells.built(case, setup.adapter, setup.folder), record)
        self.assertEqual(tells.shown(case, record, blob, names, held), [])
        rest = next(entry for entry in held.values())[len("file ") + 64:]
        digest = hashlib.sha256(ARM_TEXT).hexdigest()
        read = lambda found: ARM_TEXT if found == digest else blob(found)
        planted = copy.deepcopy(record)
        planted["files_after"]["docs/arms.md"] = entry = f"file {digest}{rest}"
        arms = ["without_skill", "with_skill", "previous_version"]
        self.assertEqual(tells.shown(case, planted, read, names, {**held, "docs/arms.md": entry}), [])
        self.assertEqual(tells.shown(case, planted, read, names, held), arms)  # not proven held by both arms
        planted["diff"]["docs/arms.md"] = {"before": None, "after": entry}  # the run wrote it
        self.assertEqual(tells.shown(case, planted, read, names, {**held, "docs/arms.md": entry}), arms)
        planted = copy.deepcopy(record)
        planted["final_message"] = "Done in with_skill.\n"  # outside every file
        self.assertEqual(tells.shown(case, planted, blob, names, held), ["with_skill"])

    def test_a_file_is_held_by_both_arms_only_when_each_built_arm_has_the_records_bytes(self):
        setup, case, record, blob, _ = self.page()
        held = tells.shared(tells.built(case, setup.adapter, setup.folder), record)
        self.assertTrue(held)
        for path, entry in held.items():
            self.assertNotIn(path, record["diff"])
            self.assertEqual(record["files_after"][path], entry)
        path, build = sorted(held)[0], tells.world.build

        def edited(case, adapter, out, *args, with_skill=False, **kwargs):  # the with-skill arm holds it changed
            arm = build(case, adapter, out, *args, with_skill=with_skill, **kwargs)
            if with_skill:
                with open(arm.path / path, "ab") as file:
                    file.write(b"one more line\n")
            return arm
        with mock.patch.object(tells.world, "build", edited):
            self.assertNotIn(path, tells.shared(tells.built(case, setup.adapter, setup.folder), record))
        changed = copy.deepcopy(record)
        changed["files_after"][path] = f"file {'0' * 64}{held[path][len('file ') + 64:]}"
        self.assertNotIn(path, tells.shared(tells.built(case, setup.adapter, setup.folder), changed))

    def test_a_plant_goes_only_on_a_page_whose_clean_view_names_nothing_it_would(self):
        setup, case, record, blob, names = self.page()
        arms, named = tells.built(case, setup.adapter, setup.folder), lambda layer: [layer["skill"], *evidence.places(
            layer)]
        page = (None, record, blob, [])
        self.assertEqual([p for p, _ in tells.clean(case, [page], arms, named)[0]], [page])
        nested = sorted(p for p in tells.shared(arms, record) if "/" in p)[0]
        beside = copy.deepcopy(record)  # the overlay adds a path the world also holds under a folder of its own
        beside["overlay"]["release"] = [nested.split("/", 1)[1]]
        self.assertEqual(tells.clean(case, [(None, beside, blob, [])], arms, named), ([], []))
        leaked = copy.deepcopy(record)
        leaked["final_message"] = f"I used {record['overlay']['skill']}.\n"
        self.assertEqual(tells.clean(case, [(None, leaked, blob, [])], arms, named)[1], [])  # the view drops the line
        with mock.patch.object(view, "text", lambda value, *args: value):  # a view that keeps the skill's name
            self.assertEqual(tells.clean(case, [(None, leaked, blob, [])], arms, named)[1],
                             [record["overlay"]["skill"]])


if __name__ == "__main__":
    unittest.main()
