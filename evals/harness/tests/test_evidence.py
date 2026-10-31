"""Evidence: the action log's observed and inferred entries, the world diff, bundles and the grader view."""

import json
import unittest

from helpers import TempCase

import hosts
import evidence
from cases import tree

CODEX = hosts.load("codex")


def codex_command(command, output="", code=0):
    return {"type": "item.completed", "item": {"type": "command_execution", "command": command,
                                               "aggregated_output": output, "exit_code": code, "status": "completed"}}


class EvidenceFaults(TempCase):
    def test_hf08_inferred_reads(self):
        events = [codex_command("/bin/bash -lc 'python3 -c \"print(open(\\\"notes/a.md\\\").read())\"'"),
                  codex_command("/bin/bash -lc 'ls skills/haiku-writer/SKILL.md'"),
                  codex_command("/bin/bash -lc 'sed -n 1,40p skills/haiku-writer/SKILL.md'")]
        log = CODEX.actions(events)
        inferred = [e for e in log if e["source"] == "inferred"]
        self.assertTrue(inferred)
        self.assertEqual({e["kind"] for e in inferred}, {"read", "skill_load"})
        # `ls` names the file without reading it: no read is inferred from it.
        self.assertNotIn("ls skills", " ".join(str(e.get("path")) for e in inferred))
        decidable = evidence.decidable(log)
        self.assertEqual({e["kind"] for e in decidable}, {"command"})
        self.assertTrue(all(e["source"] == "observed" for e in decidable))

    def test_a_log_without_a_source_is_refused(self):
        with self.assertRaises(evidence.EvidenceError):
            evidence.decidable([{"kind": "read", "path": "a"}])
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate([{"kind": "guess", "source": "observed"}])


class Bundles(TempCase):
    def world(self):
        folder = self.tmp / "world"
        (folder / "skills" / "haiku-writer").mkdir(parents=True)
        (folder / "skills" / "haiku-writer" / "SKILL.md").write_text("haiku-writer instructions\n")
        (folder / "AGENTS.md").write_text("# Rules\n| haiku-writer | skills/haiku-writer/SKILL.md | poems |\n")
        (folder / "poem.txt").write_text("old\n")
        return folder

    def test_world_diff_leaves_out_ignored_paths(self):
        folder = self.world()
        before = tree(folder)
        (folder / "poem.txt").write_text("new\n")
        (folder / "skills" / "haiku-writer" / "notes.md").write_text("x")
        (folder / ".cache").mkdir()
        (folder / ".cache" / "x").write_text("x")
        diff = evidence.world_diff(before, folder, ignore=["skills/haiku-writer", ".cache"])
        self.assertEqual(diff, {"added": [], "changed": ["poem.txt"], "removed": []})

    def test_the_grader_view_cannot_tell_the_arm(self):
        folder = self.world()
        record = {"arm": "with_skill", "final": "I used haiku-writer to write it.",
                  "diff": {"added": ["skills/haiku-writer/x"], "changed": ["poem.txt"], "removed": []},
                  "actions": [{"kind": "skill_load", "source": "observed", "name": "haiku-writer"},
                              {"kind": "read", "source": "observed", "path": "skills/haiku-writer/SKILL.md"},
                              {"kind": "write", "source": "observed", "path": "poem.txt"}]}
        bundle = self.tmp / "bundle"
        hits = evidence.write_bundle(bundle, record, folder, ["sk-secret-value"], ["HWCANARY-x"])
        self.assertEqual(hits, [])
        row = "| haiku-writer | skills/haiku-writer/SKILL.md | poems |"
        view = evidence.grader_view(bundle, self.tmp / "view", ["skills/haiku-writer"], ["haiku-writer"], [row])
        text = (view / "bundle.json").read_text()
        files = sorted(p.relative_to(view / "files").as_posix() for p in (view / "files").rglob("*") if p.is_file())
        self.assertEqual(files, ["AGENTS.md", "poem.txt"])
        self.assertNotIn("haiku-writer", text + (view / "files" / "AGENTS.md").read_text())
        self.assertNotIn("with_skill", text)
        data = json.loads(text)
        self.assertEqual([e["kind"] for e in data["actions"]], ["write"])
        self.assertEqual(data["diff"]["added"], [])

    def test_the_grader_view_keeps_empty_folders(self):
        folder = self.world()
        (folder / "out" / "empty").mkdir(parents=True)
        evidence.write_bundle(self.tmp / "b", {"final": ""}, folder, [], [])
        view = evidence.grader_view(self.tmp / "b", self.tmp / "v", ["skills/haiku-writer"], ["haiku-writer"])
        self.assertTrue((view / "files" / "out" / "empty").is_dir())
        self.assertFalse((view / "files" / "skills" / "haiku-writer").exists())

    def test_both_arms_give_the_same_grader_view(self):
        import world
        from test_world import Adapter
        self.skill()
        case = self.case({"README.md": "Notes app.\n", "docs/empty/.keep": ""}, name="views")
        (case.world / "docs/empty/.keep").unlink()
        record = {"mode": "task", "final": "done", "actions": [], "diff": {}}
        views = []
        for with_skill in (False, True):
            arm = world.build(case, Adapter, self.tmp / f"arm{with_skill}", with_skill, self.tmp / "skills")
            bundle = self.tmp / f"bundle{with_skill}"
            evidence.write_bundle(bundle, dict(record, arm=arm.arm), arm.path, [], [])
            view = evidence.grader_view(bundle, self.tmp / f"view{with_skill}",
                                        ["skills/haiku-writer", ".host/skills/haiku-writer"], ["haiku-writer"])
            views.append({p.relative_to(view).as_posix(): p.read_bytes() if p.is_file() else None
                          for p in view.rglob("*")})
        self.assertEqual(views[0], views[1])
        self.assertIn("files/docs/empty", views[0])

    def test_symlinks_never_reach_a_bundle(self):
        folder = self.world()
        outside = self.tmp / "outside.txt"
        outside.write_text("sk-secret-value HWCANARY-link\n")
        (folder / "report.txt").symlink_to(outside)
        hits = evidence.write_bundle(self.tmp / "b", {"final": ""}, folder, ["sk-secret-value"], ["HWCANARY-link"])
        self.assertEqual(hits, [])
        report = self.tmp / "b" / "files" / "report.txt"
        self.assertFalse(report.is_symlink())
        self.assertEqual(report.read_text(), f"symlink to {outside}\n")

    def test_credentials_with_escaped_characters_are_redacted(self):
        folder = self.world()
        for secret in ('sk-back\\slash-0123', 'sk-"quote"-0123', "sk-new\nline-0123", "sk-ünï-0123"):
            with self.subTest(secret=secret):
                bundle = self.tmp / f"b{abs(hash(secret))}"
                evidence.write_bundle(bundle, {"final": f"key {secret}", secret: [secret]}, folder, [secret], [])
                text = (bundle / "bundle.json").read_text()
                self.assertNotIn(secret, json.dumps(json.loads(text)) + str(json.loads(text)))

    def test_the_grader_view_keeps_only_allowed_fields(self):
        folder = self.world()
        record = {"mode": "task", "final": "done", "exposed_skills": ["haiku-writer"], "model": "m",
                  "host_version": "v", "seconds": 3, "arm": "with_skill", "actions": [], "diff": {}}
        evidence.write_bundle(self.tmp / "b", record, folder, [], [])
        view = evidence.grader_view(self.tmp / "b", self.tmp / "v", ["skills/haiku-writer"], ["haiku-writer"])
        self.assertEqual(set(json.loads((view / "bundle.json").read_text())), {"mode", "final", "actions", "diff"})

    def test_binary_files_are_scrubbed_too(self):
        folder = self.world()
        (folder / "artifact.bin").write_bytes(b"\xff\xfe sk-secret-value HWCANARY-bin \x00")
        hits = evidence.write_bundle(self.tmp / "b", {"final": ""}, folder, ["sk-secret-value"], ["HWCANARY-bin"])
        self.assertEqual(hits, ["HWCANARY-bin"])
        data = (self.tmp / "b" / "files" / "artifact.bin").read_bytes()
        self.assertNotIn(b"sk-secret-value", data)
        self.assertIn(evidence.REDACTED.encode(), data)

    def test_the_grader_view_drops_commands_that_show_the_skill(self):
        folder = self.world()
        skill = "Count the syllables of every line twice before you answer, five then seven then five."
        record = {"actions": [
            {"kind": "command", "source": "observed", "command": "cat .agents/skills/x/SKILL.md", "output": skill},
            {"kind": "command", "source": "observed", "command": "sed -n 1,9p notes.md", "output": skill},
            {"kind": "command", "source": "observed", "command": "go test ./...", "output": "ok"}]}
        evidence.write_bundle(self.tmp / "b", record, folder, [], [])
        view = evidence.grader_view(self.tmp / "b", self.tmp / "v", ["skills/haiku-writer", ".agents/skills/x"],
                                    ["haiku-writer"], skill_texts=[skill])
        commands = [e["command"] for e in json.loads((view / "bundle.json").read_text())["actions"]]
        self.assertEqual(commands, ["go test ./..."])

    def test_canaries_in_a_bundle_are_reported(self):
        folder = self.world()
        (folder / "leak.txt").write_text("HWCANARY-abc\n")
        self.assertEqual(evidence.write_bundle(self.tmp / "b", {"final": ""}, folder, [], ["HWCANARY-abc"]),
                         ["HWCANARY-abc"])


if __name__ == "__main__":
    unittest.main()
