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
import world

LONG = AGENTS + "x" * 5000 + "\n"  # longer than the output a grader sees, with the row before the cut
LISTED = [{"do": "write", "path": "notes.txt", "text": "hi\n"},
          {"do": "command", "command": "pwd && ls -a && ls skills; find . | sort && wc -l AGENTS.md"},
          {"do": "command", "command": "cat AGENTS.md && cp AGENTS.md copy.md && sed -i 's/ | /|/g' AGENTS.md"},
          {"do": "say", "text": "Done."}]
RESTORED = [{"do": "command", "command": f"printf '%s' '{LONG}' > AGENTS.md"},  # the index without its row
            {"do": "command", "command": "rm -rf skills && echo x > skills"}]  # a folder above the skill replaced
SKILL_ONLY = [{"do": "skill", "name": "haiku-writer"}, {"do": "command", "command": "cat skills/haiku-writer/SKILL.md"}]


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Views(TempCase):
    """The fake host runs in a real jail; each arm's bundle is stored, read back and viewed."""

    run_of = test_evidence.Bundles.run_of

    def views(self, same, files=None, skill_only=SKILL_ONLY):
        folder = self.skill()
        for path, content in (files or {}).get("skill", {}).items():
            (folder / path).parent.mkdir(parents=True, exist_ok=True)
            (folder / path).write_text(content)
            self.track(folder.parent)
        world = {"README.md": "A notes app.\n", "AGENTS.md": LONG, **(files or {}).get("world", {})}
        case = self.case(world, {"index": INDEX})
        views = {}
        for arm, actions in ((True, skill_only + same), (False, same)):
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
        for item in shown["log"]:
            fields = ("kind", "source", *host.ENTRIES[item["kind"]])
            fields = view.COMMAND_FIELDS if item["kind"] == "command" else fields
            self.assertEqual(set(item), set(fields))
        return shown, blobs

    def test_the_same_run_in_either_arm_gives_the_same_view(self):
        shown, blobs = self.views(LISTED)
        commands = [item["command"] for item in shown["log"] if item["kind"] == "command"]
        self.assertEqual(commands, [LISTED[1]["command"], LISTED[2]["command"]])  # what the agent ran, no output
        self.assertEqual(shown["final_message"], "Done.")
        self.assertEqual(shown["log"][0]["sha256"], host.sha256("hi\n"))
        self.assertEqual(sorted(shown["diff"]), ["AGENTS.md", "copy.md", "notes.txt"])
        self.assertEqual(blobs[shown["files_after"]["copy.md"].split(" ")[1]].decode(), LONG)

    def test_a_read_inferred_from_a_command_on_the_overlay_goes_with_it(self):
        guide = "references/guide.md"  # one name in the skill and in the world, so the command names both
        shown, _ = self.views(LISTED, {"skill": {guide: "x\n"}, "world": {"docs/guide.md": "y\n"}},
                              [{"do": "command", "command": f"cat skills/haiku-writer/{guide}"}])
        self.assertNotIn("docs/guide.md", [item.get("path") for item in shown["log"]])

    def test_a_command_on_the_overlay_hides_no_read_of_a_later_command(self):
        guide = "references/guide.md"
        shown, _ = self.views([{"do": "command", "command": "cat docs/guide.md"}],
                              {"skill": {guide: "x\n"}, "world": {"docs/guide.md": "y\n"}},
                              [{"do": "command", "command": f"cat skills/haiku-writer/{guide}"}])
        self.assertIn("docs/guide.md", [item.get("path") for item in shown["log"]])

    def test_a_change_only_to_the_overlay_is_no_change(self):
        shown, _ = self.views(RESTORED)
        self.assertEqual(shown["diff"], {"skills": {"before": None, "after": shown["files_after"]["skills"]}})

    def test_an_action_is_the_overlay_s_when_it_loads_or_names_the_skill(self):
        words = world.names(["haiku-writer", "skills/haiku-writer"])
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
        test = world.names(["test", "skills/test"])  # a skill's name is found only as a whole name
        self.assertFalse(view.on_overlay({"kind": "command", "source": "observed", "command": "pytest -q"}, test))
        cat = {"kind": "command", "source": "observed", "command": "cat skills/test/a"}
        self.assertTrue(view.on_overlay(cat, test))
        self.assertEqual(view.text("def test_save():\nuse test.\n", test, {}), "def test_save():\n")
        self.assertEqual(view._relative("/x/w/notes.txt", "/x/w"), "notes.txt")  # a host may report it absolute
        self.assertEqual(view.text("我使用test技能\n", test, {}), "")  # the same for text as for bytes


if __name__ == "__main__":
    unittest.main()
