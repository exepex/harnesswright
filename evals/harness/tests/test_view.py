"""The grader view: everything the run wrote and said, without what the harness put there (`view.ADDED`), so the
same run in either arm gives the same view when only the install and its load differ."""

import json
import unittest

from helpers import TempCase
from test_evidence import JAIL
from test_world import AGENTS, INDEX

import evidence
import host
import test_evidence
import view

LONG = AGENTS + "x" * 5000 + "\n"  # longer than the output a grader sees, with the row inside it
LISTED = [{"do": "write", "path": "notes.txt", "text": "hi\n"},
          {"do": "command", "command": "pwd && ls -a && ls skills; find . | sort && wc -l AGENTS.md"},
          {"do": "command", "command": "cat AGENTS.md && cp README.md copy.md && printf '| other | x |\\n' >> AGENTS.md"},
          {"do": "say", "text": "Done."}]
RESTORED = [{"do": "command", "command": f"printf '%s' '{LONG}' > AGENTS.md"},  # the index without its row
            {"do": "command", "command": "rm -rf skills && echo x > skills"}]  # a folder above the skill replaced
LOAD = [{"do": "skill", "name": "haiku-writer"}]
SKILL = "skills/haiku-writer/SKILL.md"


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Views(TempCase):
    """The fake host runs in a real jail; each arm's bundle is stored, read back and viewed."""

    run_of = test_evidence.Bundles.run_of

    def views(self, same, skill_only=LOAD, equal=True):
        case = self.case({"README.md": "A notes app.\n", "AGENTS.md": LONG}, {"index": INDEX})
        views = {}
        for arm, actions in ((True, skill_only + same), (False, same)):
            out = evidence.store(*self.run_of(actions, arm=arm, case=case), self.tmp / f"bundle-{arm}")
            record, blob = evidence.load(out)
            self.assertIn("haiku-writer", json.dumps(record))  # the full bundle keeps the overlay for audits
            views[arm] = view.view(record, blob)
        self.assertEqual(views[True] == views[False], equal)
        shown, blobs = views[True]
        self.assertEqual(tuple(shown), view.FIELDS)
        self.assertNotIn(str(self.tmp), json.dumps(shown) + b"".join(blobs.values()).decode())
        self.assertFalse([path for path in shown["files_after"] if path.startswith(("skills/", ".fake/skills"))])
        for item in shown["log"]:
            fields = ("kind", "source", *host.ENTRIES[item["kind"]])
            self.assertEqual(set(item), set(view.COMMAND_FIELDS if item["kind"] == "command" else fields))
        return shown, blobs

    def test_the_same_run_in_either_arm_gives_the_same_view(self):
        shown, blobs = self.views(LISTED)
        self.assertEqual([item["command"] for item in shown["log"] if item["kind"] == "command"],
                         [LISTED[1]["command"], LISTED[2]["command"]])  # as the agent ran them, no output
        self.assertEqual(shown["final_message"], "Done.")
        self.assertEqual(shown["log"][0]["sha256"], host.sha256("hi\n"))
        self.assertEqual(sorted(shown["diff"]), ["AGENTS.md", "copy.md", "notes.txt"])
        self.assertEqual(blobs[shown["files_after"]["AGENTS.md"].split(" ")[1]].decode(), LONG + "| other | x |\n")

    def test_what_the_run_wrote_and_said_of_the_skill_stays(self):
        mine = [{"do": "command", "command": f"cat {SKILL}"}, {"do": "write", "path": "rules-text-haiku-writer.core.md",
                                                               "text": "rules\n"},
                {"do": "write", "path": "haiku-writer_draft.md", "text": "draft\n"}, {"do": "say", "text": "I used "
                                                                                                         "haiku-writer."}]
        shown, _ = self.views([], LOAD + mine, equal=False)
        self.assertEqual([item["command"] for item in shown["log"] if item["kind"] == "command"], [f"cat {SKILL}"])
        self.assertNotIn("skill", [item["kind"] for item in shown["log"]])  # the load the lead line pins goes
        self.assertNotIn(SKILL, [item.get("path") for item in shown["log"]])
        self.assertLessEqual({"rules-text-haiku-writer.core.md", "haiku-writer_draft.md"}, set(shown["files_after"]))
        self.assertEqual(shown["final_message"], "I used haiku-writer.")

    def test_a_change_only_to_the_overlay_is_no_change(self):
        shown, _ = self.views(RESTORED)
        self.assertEqual(shown["diff"], {"skills": {"before": None, "after": shown["files_after"]["skills"]}})

    @staticmethod
    def record(log, final=None, files_after=None):
        overlay = {"skill": "haiku-writer", "paths": ["skills/haiku-writer", ".fake/skills/haiku-writer"],
                   "index": "AGENTS.md", "row": "| haiku-writer | x |", "index_without": None}
        return {"overlay": overlay, "folders": {"/x/w": "/run/project"}, "own_files": [], "diff": {}, "case": None,
                "mode": "task", "files_after": files_after or {}, "final_message": final, "log": log}

    def test_the_view_removes_the_lead_line_and_its_load_and_keeps_every_other_action(self):
        lead = host.LEAD.format(skill="haiku-writer", path=".fake/skills/haiku-writer/SKILL.md")
        command = host.entry("command", command=f"python3 skills/haiku-writer/x.py; cat /x/w/{SKILL}", exit_code=1,
                             output="haiku-writer says no")
        log = [host.entry("skill", name="haiku-writer"), host.entry("skill", "inferred", name="other"),
               host.entry("read", path=SKILL), host.entry("read", "inferred", path=f"/x/w/{SKILL}"),
               host.entry("read", path="skills/haiku-writer/references/a.md"), command,
               host.entry("message", text=f"I read it:\n{lead}\nI used haiku-writer.")]
        shown = view.view(self.record(log, f"{lead}\nDone in /x/w."), None)[0]
        self.assertEqual(shown["log"], [host.entry("skill", "inferred", name="other"), log[4], {
            "kind": "command", "source": "observed", "command": f"python3 skills/haiku-writer/x.py; cat "
                                                                 f"/run/project/{SKILL}"},
            host.entry("message", text="I read it:\nI used haiku-writer.")])
        self.assertEqual(shown["final_message"], "Done in /run/project.")

    def test_the_index_row_goes_only_where_the_install_put_it(self):
        row, digest = b"| haiku-writer | x |", lambda data: "file " + host.sha256(data)
        data = {b"index": b"| Skill |\n" + row + b"\r\n", b"copy": row + b"\n", b"changed": b"| haiku-writer | y |\n"}
        files = {"AGENTS.md": digest(data[b"index"]), "copy.md": digest(data[b"copy"]),
                 "docs/AGENTS.md": digest(data[b"changed"])}
        shown, blobs = view.view(self.record([], None, files), {host.sha256(v): v for v in data.values()}.__getitem__)
        self.assertEqual({path: blobs[entry.split(" ")[1]] for path, entry in shown["files_after"].items()},
                         {"AGENTS.md": b"| Skill |\n", "copy.md": row + b"\n", "docs/AGENTS.md": data[b"changed"]})
        leads = view.lead_lines({"skill": "s", "paths": ["d"]})
        self.assertEqual(view.text(b"a\n" + leads[0].encode() + b" ok\nb /x/w\n", leads, {"/x/w": "/r"}), b"a\nb /r\n")
        self.assertEqual(view._relative("/x/w/notes.txt", "/x/w"), "notes.txt")  # a host may report it absolute


if __name__ == "__main__":
    unittest.main()
