"""The grader view: built from a bundle by allow lists and three rules, it is the same for the same run in either
arm."""

import json
import unittest

from helpers import TempCase
from test_evidence import JAIL
from test_world import AGENTS, INDEX

import evidence
import host
import test_evidence
import view

LONG = AGENTS + "x" * 5000 + "\n"  # longer than the output a grader sees, with the row before the cut
LISTED = [{"do": "write", "path": "notes.txt", "text": "hi\n"},
          {"do": "command", "command": "pwd && find . -type f -not -path './.git/*' | sort"},
          {"do": "command", "command": "cat AGENTS.md && cp AGENTS.md copy.md && sed -i 's/ | /|/g' AGENTS.md"},
          {"do": "say", "text": "Done."}]
RESTORED = [{"do": "command", "command": f"printf '%s' '{LONG}' > AGENTS.md"},  # the index without its row
            {"do": "command", "command": "rm -rf skills && echo x > skills"}]  # a folder above the skill replaced
SKILL_ONLY = [{"do": "skill", "name": "haiku-writer"}, {"do": "command", "command": "cat skills/haiku-writer/SKILL.md"}]


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Views(TempCase):
    """The fake host runs in a real jail; each arm's bundle is stored, read back and viewed."""

    run_of = test_evidence.Bundles.run_of

    def views(self, same):
        self.skill()
        case = self.case({"README.md": "A notes app.\n", "AGENTS.md": LONG}, {"index": INDEX})
        views = {}
        for arm, actions in ((True, SKILL_ONLY + same), (False, same)):
            out = evidence.store(*self.run_of(actions, arm=arm, case=case), self.tmp / f"bundle-{arm}")
            record, blob = evidence.load(out)
            self.assertIn("haiku-writer", json.dumps(record))  # the full bundle keeps the overlay for audits
            views[arm] = view.view(record, blob)
        self.assertEqual(views[True], views[False])
        shown, blobs = views[True]
        self.assertEqual(tuple(shown), view.FIELDS)
        text = json.dumps(shown) + b"".join(blobs.values()).decode()
        for word in ("haiku-writer", "SKILL.md", str(self.tmp)):
            self.assertNotIn(word, text)
        named = [*shown["files_after"].values(), *(c["after"] for c in shown["diff"].values() if c["after"])]
        self.assertEqual({entry.split(" ")[1] for entry in named if entry.startswith("file")}, set(blobs))
        host.check_log(shown["log"])
        return shown, blobs

    def test_the_same_run_in_either_arm_gives_the_same_view(self):
        shown, blobs = self.views(LISTED)
        commands = [item for item in shown["log"] if item["kind"] == "command"]
        self.assertEqual(len(commands), 2)  # a listing that shows the skill is kept, without the skill's lines
        self.assertIn("./notes.txt", commands[0]["output"])
        self.assertTrue(commands[0]["output"].startswith("/run/project\n"))  # the run's folder in a neutral word
        self.assertEqual(len(commands[1]["output"]), host.OUTPUT_LIMIT)  # cut after the row's line went
        self.assertEqual(shown["final_message"], "Done.")
        self.assertEqual(shown["log"][0]["sha256"], host.sha256("hi\n"))
        self.assertEqual(sorted(shown["diff"]), ["AGENTS.md", "copy.md", "notes.txt"])
        self.assertEqual(blobs[shown["files_after"]["copy.md"].split(" ")[1]].decode(), LONG)

    def test_a_change_only_to_the_overlay_is_no_change(self):
        shown, _ = self.views(RESTORED)
        self.assertEqual(shown["diff"], {"skills": {"before": None, "after": shown["files_after"]["skills"]}})

    def test_an_action_is_the_overlay_s_when_it_loads_or_names_the_skill(self):
        words = ["haiku-writer", "skills/haiku-writer"]
        for item, mine in (({"kind": "skill", "source": "observed", "name": "x"}, True),
                           ({"kind": "read", "source": "inferred", "path": "skills/haiku-writer/SKILL.md"}, True),
                           ({"kind": "command", "source": "observed", "command": "ls skills/haiku-writer"}, True),
                           ({"kind": "command", "source": "observed", "command": "ls", "output": "haiku-writer"},
                            False),
                           ({"kind": "message", "source": "observed", "text": "I used haiku-writer"}, False)):
            with self.subTest(item=item):
                self.assertEqual(view.on_overlay(item, words), mine)
        self.assertEqual(view.text("a\n| haiku-writer |\r\nb /x/w/c", words, {"/x/w": "/run/project"}),
                         "a\nb /run/project/c")
        self.assertEqual(view.text(b"a\n|haiku-writer|\n", words, {}), b"a\n")


if __name__ == "__main__":
    unittest.main()
