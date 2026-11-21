"""Proven use (doc 12): the one load reader, the `not loaded` status of a pinned run, its label and the round stop."""

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from helpers import TempCase
from test_adapters import CLAUDE
from test_labels import CONTRACT, verdict

import evidence
import gates
import labels
import runs

TEXT = "---\nname: haiku-writer\ndescription: Writes a haiku.\n---\n\n# Haiku writer\n\nCount every syllable.\n"
PATHS = ["skills/haiku-writer", ".fake/skills/haiku-writer"]
WORLD = "/tmp/r-1/run/world"


def entry(kind, source="observed", **fields):
    return {"kind": kind, "source": source, **fields}


def command(text, output, source="observed"):
    return entry("command", source, command=text, exit_code=0, output=output)


def loaded(*log, text=TEXT):
    record = {"log": list(log), "folders": {WORLD: "/run/project", "/tmp/r-1/run/home": "/run/home"}}
    return evidence.loaded(record, "haiku-writer", PATHS, text)


class Reader(unittest.TestCase):
    def test_the_hosts_own_skill_event_for_the_skill_proves_a_load(self):
        self.assertTrue(loaded(entry("skill", name="haiku-writer")))
        self.assertFalse(loaded(entry("skill", name="limerick-writer")))

    def test_an_observed_read_of_the_exact_skill_md_of_either_copy_proves_a_load(self):
        for path in ("skills/haiku-writer/SKILL.md", ".fake/skills/haiku-writer/SKILL.md",
                     "./skills/haiku-writer/SKILL.md", f"{WORLD}/.fake/skills/haiku-writer/SKILL.md"):
            with self.subTest(path=path):
                self.assertTrue(loaded(entry("read", path=path)))

    def test_a_read_of_another_skill_md_or_another_file_of_the_skill_proves_nothing(self):
        for path in ("skills/limerick-writer/SKILL.md", "release/haiku-writer/SKILL.md",
                     "skills/haiku-writer/references/notes.md", "/elsewhere/skills/haiku-writer/SKILL.md"):
            with self.subTest(path=path):
                self.assertFalse(loaded(entry("read", path=path)))

    def test_inferred_entries_alone_never_prove_a_load(self):
        self.assertFalse(loaded(command("cat skills/haiku-writer/SKILL.md", TEXT, source="inferred"),
                                entry("read", "inferred", path="skills/haiku-writer/SKILL.md"),
                                entry("skill", "inferred", name="haiku-writer")))

    def test_a_command_that_prints_the_whole_skill_md_it_names_proves_a_load(self):
        for text in ("cat skills/haiku-writer/SKILL.md", f"cat '{WORLD}/skills/haiku-writer/SKILL.md'",
                     "cat -- .fake/skills/haiku-writer/SKILL.md"):
            with self.subTest(command=text):
                self.assertTrue(loaded(command(text, TEXT.rstrip("\n"))))

    def test_a_search_over_the_release_that_shows_the_skill_text_proves_nothing(self):
        self.assertFalse(loaded(command("grep -r '' release/", TEXT)))
        self.assertFalse(loaded(command("cat release/haiku-writer/SKILL.md", TEXT)))

    def test_through_the_claude_code_adapter_a_read_tool_call_proves_a_load_and_a_grep_does_not(self):
        def logged(name, tool_input, output):
            stdout = "".join(json.dumps(event) + "\n" for event in (
                {"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "id": "1", "name": name, "input": tool_input}]}},
                {"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": "1", "content": [{"type": "text", "text": output}]}]}}))
            return CLAUDE.action_log(stdout, None)

        path = f"{WORLD}/.claude/skills/haiku-writer/SKILL.md"
        paths = ["skills/haiku-writer", ".claude/skills/haiku-writer"]
        for name, tool_input, output, proves in (
                ("Read", {"file_path": path}, TEXT, True),
                ("Grep", {"pattern": "Count", "path": path}, "8:Count every syllable.", False),
                ("Grep", {"pattern": "zzz", "path": path}, "No matches found", False)):
            with self.subTest(tool=name, pattern=tool_input.get("pattern")):
                record = {"log": logged(name, tool_input, output), "folders": {WORLD: "/run/project"}}
                self.assertEqual(evidence.loaded(record, "haiku-writer", paths, TEXT), proves)

    def test_a_command_that_names_the_skill_md_but_prints_part_of_it_proves_nothing(self):
        self.assertFalse(loaded(command("cat skills/haiku-writer/SKILL.md | head -3", TEXT[:40])))
        self.assertFalse(loaded(command("grep -n Count skills/haiku-writer/SKILL.md", "8:Count every syllable.")))
        self.assertFalse(loaded(command("cat 'skills/haiku-writer/SKILL.md", TEXT)))  # cannot be split
        self.assertFalse(loaded(command("cat skills/haiku-writer/SKILL.md", ""), text=""))


def made(number, status, arm="with_skill", case="c1", pinned=True):
    return {"host": "h", "skill": "haiku-writer", "case": case, "arm": arm, "number": number, "key": f"k{number}",
            "status": status, **({"pinned": True} if pinned else {})}


class Pinned(TempCase):
    def test_only_a_task_run_with_the_skill_or_its_previous_version_in_a_pinned_round_is_pinned(self):
        task, trigger = types.SimpleNamespace(kind="task"), types.SimpleNamespace(kind="trigger")
        self.assertTrue(runs.pinned({"pinned": True}, task, "with_skill"))
        self.assertTrue(runs.pinned({"pinned": True}, task, runs.PREVIOUS))
        self.assertFalse(runs.pinned({"pinned": True}, task, "without_skill"))
        self.assertFalse(runs.pinned({"pinned": True}, trigger, "with_skill"))
        self.assertFalse(runs.pinned({}, task, "with_skill"))  # no manifest pins a load yet

    def gate(self, statuses, pinned=True):
        """The run gate over one task case with each with-skill run's (status, tries not loaded) in `statuses`."""
        folder = Path(tempfile.mkdtemp(dir=self.tmp))
        case = types.SimpleNamespace(skill="haiku-writer", id="c1", kind="task")
        record = {"plan": {"runs": len(statuses)}, "cases": {"haiku-writer": {"c1": "0" * 64}},
                  **({"pinned": True} if pinned else {})}
        r = types.SimpleNamespace(record=record, store=None, folder=folder, cases={("haiku-writer", "c1"): case},
                                  hosts={"h": {"drift": {}}}, modules={"h": None}, version=lambda host: None,
                                  timeout=1, repo=None, containment={}, runs=[])

        def run(record, store, case, arm, host, number, *args, **options):
            status, missed = statuses[number - 1] if arm == "with_skill" else ("made", 0)
            if missed:
                (folder / "runs" / f"{arm}{number}").mkdir(parents=True)
                (folder / "runs" / f"{arm}{number}" / runs.UNLOADED).write_text(json.dumps({"reasons": ["-"] * missed}))
            return {"key": f"{arm}{number}", "status": status, "bundle": None}
        with mock.patch.object(runs, "run", run):
            return gates.run_gate(r)

    def test_half_or_more_pinned_tries_not_loaded_stop_the_round_as_a_harness_fault(self):
        with self.assertRaisesRegex(gates.Stop, "harness fault: 2 of 4 pinned tries are not loaded"):
            self.gate([("not loaded", 2), ("made", 0), ("kept", 0)])
        with self.assertRaisesRegex(gates.Stop, "harness fault: 3 of 6 pinned tries are not loaded"):
            self.gate([("made", 1)] * 3)  # every slot misses once, then loads
        found = self.gate([("not loaded", 2), ("made", 0), ("kept", 0), ("void", 0), ("made", 0)])
        self.assertEqual([m.get("pinned", False) for m in found if m["arm"] == "with_skill"], [True] * 5)
        self.assertFalse(any(m.get("pinned") for m in found if m["arm"] == "without_skill"))
        self.assertEqual(len(self.gate([("not loaded", 2)] * 2, pinned=False)), 4)  # not pinned: no stop


class Label(TempCase):
    def test_a_not_loaded_run_and_a_case_with_no_loaded_run_are_named_and_keep_it_inconclusive(self):
        expectations = [{"text": "The notes are kept", "source": CONTRACT,
                         "check": {"name": "file_state", "args": {"path": "README.md", "state": "unchanged"}}}]
        task = types.SimpleNamespace(skill="haiku-writer", kind="task", expectations=expectations, siblings=[],
                                     tools=[])
        found = [made(1, "not loaded", case="c1"), made(2, "not loaded", case="c2"), made(3, "made", case="c2"),
                 *[made(n, "made", "without_skill", case, False) for n, case in ((4, "c1"), (5, "c2"))]]
        for item in found[2:]:
            (self.tmp / "runs" / item["key"]).mkdir(parents=True)
            (self.tmp / "runs" / item["key"] / "checks.json").write_text(json.dumps({"verdicts": [verdict("pass")]}))
        (self.tmp / "attempts").mkdir()
        (self.tmp / "drift").mkdir()
        (self.tmp / "drift" / "h.json").write_text(json.dumps({"tools": {}, "own files": {}}))
        (self.tmp / "attempts" / "a1.json").write_text(json.dumps({"gates": [
            {"gate": "probe", "passed": True, "outcome": {"passed": ["h"], "not run": {}}},
            {"gate": "run", "passed": True, "outcome": found},
            {"gate": "grade", "passed": True, "outcome": {"goldens": {}, "runs": []}}]}))
        record = {"round": "r1", "commit": "0" * 40, "cases": {"haiku-writer": {"c1": "", "c2": ""}},
                  "hosts": {"h": {"model": "m", "version": {"version": "1"}}}, "kit": "0" * 64, "skills": {},
                  "adapters": {}, "plan": {"runs": 3}}  # what the label file's setup reads (`setups.setup`)
        pinned = {"with_skill": {"rate": 0.3333, "loaded": 1, "tries": 3}}
        with mock.patch.object(labels.measures, "measures", lambda *args: {("h", "haiku-writer"): {
                "pinned_load": pinned}}), mock.patch.object(labels.verdicts, "missing", lambda found: []):
            entry = labels.labels(self.tmp, "a1", record, {("haiku-writer", "c1"): task, ("haiku-writer", "c2"): task},
                                  {"date": "2026-11-20"})["skills"]["haiku-writer"]["h"]
        self.assertEqual((entry["label"], entry["pinned_load"]), ("inconclusive", pinned))
        self.assertIn("c1, with_skill, run 1: not scored (not loaded)", entry["gaps"])
        self.assertIn("c1, with_skill: no loaded run", entry["gaps"])
        self.assertNotIn("c2, with_skill: no loaded run", entry["gaps"])


if __name__ == "__main__":
    unittest.main()
