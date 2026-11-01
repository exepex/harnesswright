"""The grader view: built from a bundle by allow lists, it is the same for the same run in either arm."""

import json
import unittest

from helpers import TempCase
from test_evidence import JAIL
from test_world import AGENTS, INDEX

import evidence
import host
import test_evidence
import scrub
import view

SKILL_WORDS = ("haiku-writer", "SKILL.md", ".fake/skills")


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Views(TempCase):
    """The fake host runs in a real jail; each arm's bundle is stored, read back and viewed."""

    run_of = test_evidence.Bundles.run_of

    def test_the_same_run_in_either_arm_gives_the_same_view(self):
        self.skill()
        case = self.case({"README.md": "A notes app.\n", "AGENTS.md": AGENTS}, {"index": INDEX})
        same = [{"do": "write", "path": "notes.txt", "text": "hi\n"},
                {"do": "command", "command": "cat AGENTS.md && printf 'Note.\\n' >> AGENTS.md"},
                {"do": "say", "text": "Done with haiku-writer."}]
        skill_only = [{"do": "skill", "name": "haiku-writer"},
                      {"do": "command", "command": "cat skills/haiku-writer/SKILL.md"}]
        views = {}
        for arm, actions in ((True, skill_only + same), (False, same)):
            record, blob = evidence.load(evidence.store(*self.run_of(actions, arm=arm, case=case), self.tmp / str(arm)))
            views[arm] = view.view(record, blob)
            self.assertIn("haiku-writer", json.dumps(record))  # the full bundle keeps the overlay for audits
        (shown, blobs), (other, other_blobs) = views[True], views[False]
        self.assertEqual(shown, other)
        self.assertEqual(blobs, other_blobs)
        self.assertEqual(tuple(shown), view.FIELDS)
        text = json.dumps(shown) + b"".join(blobs.values()).decode()
        for word in SKILL_WORDS:
            self.assertNotIn(word, text)
        self.assertEqual(shown["final_message"], f"Done with {scrub.NEUTRAL_NAME}.")
        self.assertEqual(shown["diff"]["AGENTS.md"]["before"], "file")  # its kind only: the arms differ before
        index = shown["files_after"]["AGENTS.md"].split(" ")[1]
        self.assertEqual(blobs[index].decode(), AGENTS + "Note.\n")
        self.assertEqual({entry.split(" ")[1] for entry in shown["files_after"].values() if entry.startswith("file")},
                         set(blobs))  # every hash in the view names one of its blobs
        self.assertEqual(shown["log"][-1]["text"], shown["final_message"])  # a message is kept, in neutral words
        writes = [item for item in shown["log"] if item["kind"] == "write"]
        self.assertEqual(writes[0]["sha256"], host.sha256("hi\n"))
        self.assertNotIn(".fake-state", shown["files_after"])  # the host's own file is left out
        host.check_log(shown["log"])

    def test_an_entry_is_the_overlay_s_when_it_loads_or_names_the_skill(self):
        overlay = {"skill": "haiku-writer", "paths": ["skills/haiku-writer"], "row": "| haiku-writer |"}
        for item, mine in (({"kind": "skill", "source": "observed", "name": "x"}, True),
                           ({"kind": "read", "source": "inferred", "path": "skills/haiku-writer/SKILL.md"}, True),
                           ({"kind": "command", "source": "observed", "command": "ls", "exit_code": 0,
                             "output": "haiku-writer"}, True),
                           ({"kind": "read", "source": "observed", "path": "README.md"}, False)):
            with self.subTest(item=item):
                self.assertEqual(view.marked(item, overlay), mine)
        self.assertEqual(view.unrow("a\n| haiku-writer |\r\nb", overlay["row"]), "a\nb")
        self.assertEqual(view.unrow(b"a\n| haiku-writer |\n", overlay["row"]), b"a\n")
        self.assertEqual(view.unrow("a", None), "a")


if __name__ == "__main__":
    unittest.main()
