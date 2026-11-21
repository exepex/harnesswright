"""The rule of `tells`: an arm word may be only in a world file that both arms are built holding byte for byte and
the run left as built; anywhere else it counts, and the skill's names count everywhere."""

import copy
import hashlib
import random
import re
import types
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

    def test_the_skill_s_name_inside_a_longer_name_counts_and_the_view_never_shows_it(self):
        setup, case, record, blob, names = self.page()
        skill, digest = record["overlay"]["skill"], hashlib.sha256(b"rules\n").hexdigest()
        rest = next(e for e in record["files_after"].values() if e.startswith("file "))[len("file ") + 64:]
        read = lambda found: b"rules\n" if found == digest else blob(found)
        planted = copy.deepcopy(record)  # a file only the with-skill arm writes, and the run's word for it
        path = f".harness/runs/r1/rules-text-{skill}.core.md"
        planted["files_after"][path] = entry = f"file {digest}{rest}"
        planted["diff"][path] = {"before": None, "after": entry}
        planted["final_message"] = f"Read rules-text-{skill}.core.md.\nDone.\n"
        held = tells.shared(tells.built(case, setup.adapter, setup.folder), record)  # a world may name the arms
        self.assertEqual(tells.shown(case, planted, read, names, held), [])
        whole = lambda words: re.compile("(?<![\\w-])(?:" + "|".join(map(re.escape, words)) + ")(?![\\w-])", re.ASCII)
        with mock.patch.object(tells.view, "spelled", whole):  # the view as it was: whole names only
            self.assertEqual(tells.shown(case, planted, read, names, held), [skill])

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

    def test_an_overlay_path_counts_unless_it_ends_a_longer_path_of_a_file_both_arms_hold(self):
        setup, case, record, blob, _ = self.page()
        held = tells.shared(tells.built(case, setup.adapter, setup.folder), record)
        nested = sorted(p for p in held if "/" in p)[0]
        tail = nested.split("/", 1)[1]  # a release file a team install would add, which the world holds deeper down
        beside = copy.deepcopy(record)
        beside["overlay"]["release"] = [tail]
        blind = types.SimpleNamespace(**vars(evidence))
        blind.places = lambda overlay: overlay["paths"]  # a view that reads the skill's paths only, and so shows it
        with mock.patch.object(view, "evidence", blind):
            self.assertEqual(tells.shown(case, beside, blob, [tail], held), [])  # the page names the world's own file
            self.assertEqual(tells.shown(case, beside, blob, [tail], {p: e for p, e in held.items() if p != nested}),
                             [tail])  # not proven held by both arms, so it counts
        only = copy.deepcopy(beside)  # judge-a's probe: a release file, and a file of the record no built arm holds
        only["overlay"]["release"] = ["only-with.md"]
        only["files_after"]["kept/only-with.md"] = record["files_after"][nested]
        self.assertEqual(tells.shown(case, only, blob, ["only-with.md"], held), [])  # the view hides it
        with mock.patch.object(view, "evidence", blind):
            self.assertEqual(tells.shown(case, only, blob, ["only-with.md"], held), ["only-with.md"])
        kept = {nested}
        for text, inside in ((f"Read {nested}.", True), (f"Read /world/{tail}", False), (f"Read {tail}", False),
                             (f"Read other/{tail}", False), (f"Read {nested}/notes.md", False)):
            with self.subTest(text=text):
                found = re.search(f"(?<![A-Za-z0-9]){re.escape(tail)}(?![A-Za-z0-9])", text)
                self.assertEqual(tells._inside(text, found, kept), inside)

if __name__ == "__main__":
    unittest.main()
