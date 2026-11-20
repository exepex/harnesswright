"""Pinned load (doc 12, Proven use): the adapter's lead line, the runs that start with it, the manifest that pins, the
view that never shows it (and the view fault that catches one that does), and the probe that proves a pin loads,
on a probe skill as long as the longest skill the round installs, before any real run."""

import types
import unittest
from unittest import mock

from test_faults import Fake
from test_host import fake_adapter
from test_probes import JAIL, ProbeCase, acts
from test_runs import DRIFT, Round

import faults
import gates
import host
import probes
import rounds
import runs
import skills
import view

LEAD = "Load the skill haiku-writer at skills/haiku-writer/SKILL.md before anything else."


class Lead(unittest.TestCase):
    def test_every_adapter_pins_with_the_default_lead_line(self):
        for name in ("claude-code", "codex", "goose"):
            with self.subTest(adapter=name):
                adapter = rounds.adapter(name)
                self.assertEqual(host.lead(adapter, "haiku-writer", "skills/haiku-writer/SKILL.md"), LEAD)
        self.assertEqual(host.lead(fake_adapter(), "haiku-writer", "skills/haiku-writer/SKILL.md"), LEAD)

    def test_a_pin_that_is_not_one_line_naming_the_skill_and_its_path_is_refused(self):
        for line in ("Load the skill.", f"{LEAD}\nAnd more.", "Load haiku-writer first.", None):
            with self.subTest(line=line), self.assertRaises(host.HostError):
                host.lead(types.SimpleNamespace(NAME="h", pin=lambda skill, path, l=line: l), "haiku-writer",
                          "skills/haiku-writer/SKILL.md")

    def test_the_view_never_shows_the_lead_line(self):
        record = {"overlay": {"skill": "haiku-writer", "paths": ["skills/haiku-writer", ".fake/skills/haiku-writer"],
                              "index": None, "row": None, "index_without": None},
                  "folders": {}, "own_files": [], "files_after": {}, "diff": {}, "case": "c1", "mode": "task",
                  "log": [{"kind": "message", "source": "observed", "text": f"I read the task:\n{LEAD}\nDone."}],
                  "final_message": f"{LEAD}\nDone."}
        seen, _ = view.view(record, None)
        self.assertEqual((seen["log"][0]["text"], seen["final_message"]), ("I read the task:\nDone.", "Done."))


class Manifest(Round):
    def test_a_round_planned_now_pins_and_a_manifest_without_the_flag_does_not(self):
        record = self.plan()
        case = types.SimpleNamespace(kind="task", skill="haiku-writer", skill_rel="skills/haiku-writer")
        self.assertIs(record["pinned"], True)
        self.assertEqual(runs.lead(record, case, "with_skill", fake_adapter()), LEAD)
        self.assertIsNone(runs.lead({k: v for k, v in record.items() if k != "pinned"}, case, "with_skill",
                                    fake_adapter()))  # an old manifest resumes unpinned
        for arm in ("without_skill",):
            self.assertIsNone(runs.lead(record, case, arm, fake_adapter()))
        self.assertIsNone(runs.lead(record, types.SimpleNamespace(**{**vars(case), "kind": "trigger"}), "with_skill",
                                    fake_adapter()))  # trigger runs keep free choice

    def test_the_pinned_flag_and_the_lead_line_are_in_the_run_key(self):
        record = self.plan()
        unpinned = {k: v for k, v in record.items() if k != "pinned"}
        keys = {runs.key(record, "haiku-writer", "c1", "with_skill", "fakehost", 1, DRIFT, lead=LEAD),
                runs.key(record, "haiku-writer", "c1", "with_skill", "fakehost", 1, DRIFT, lead=LEAD + " Now."),
                runs.key(record, "haiku-writer", "c1", "with_skill", "fakehost", 1, DRIFT),
                runs.key(unpinned, "haiku-writer", "c1", "with_skill", "fakehost", 1, DRIFT)}
        self.assertEqual(len(keys), 4)

    def test_the_probe_skill_is_as_long_as_the_longest_skill_the_round_installs_its_previous_version_too(self):
        long = "---\nname: haiku-writer\ndescription: Writes a haiku. Use when asked for a haiku.\n---\n\n" + \
            "".join(f"Step {n}: count the syllables of this line again.\n" for n in range(700))
        (self.repo / "skills" / "haiku-writer" / "SKILL.md").write_text(long)
        record = self.plan()
        old = self.git("rev-parse", "HEAD")
        round_ = types.SimpleNamespace(record=record, repo=self.repo, skills=skills.folders(self.repo))
        self.assertEqual(gates.installed(round_), {"lines": 705, "bytes": len(long.encode())})
        (self.repo / "skills" / "haiku-writer" / "SKILL.md").write_text(long[:200] + "\n")
        record = self.plan(previous={"haiku-writer": old})  # the shorter version is under test, the longer previous
        found = gates.installed(types.SimpleNamespace(record=record, repo=self.repo, skills=skills.folders(self.repo)))
        self.assertEqual(found, {"lines": 705, "bytes": len(long.encode())})
        text = probes.skill_text({"discovery": probes.new_token()}, found)
        self.assertGreaterEqual((text.count("\n"), len(text.encode())), (705, len(long.encode())))
        self.assertNotIn("syllables", text)  # neutral text, never the skill's own


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Probe(ProbeCase):
    def test_a_host_that_loads_the_skill_its_prompt_pins_passes_and_one_that_does_not_is_not_run(self):
        self.assertIsNone(self.probe(probes.PINNED, "task", acts({"do": "skill", "name": probes.SKILL})))
        printed = acts({"do": "command", "command": f"cat .fake/skills/{probes.SKILL}/SKILL.md"})
        self.assertIsNone(self.probe(probes.PINNED, "task", printed))
        found = self.probe(probes.PINNED, "task", acts({"do": "say", "text": "Done."}))
        self.assertEqual(found, f"pinned load probe, task run: the host's log proves no load of {probes.SKILL}, "
                                f"which its prompt pinned at .fake/skills/{probes.SKILL}")
        searched = acts({"do": "command", "command": f"grep -n Probe .fake/skills/{probes.SKILL}/SKILL.md"})
        self.assertIn("proves no load", self.probe(probes.PINNED, "task", searched))

    def test_the_probe_prompt_starts_with_the_lead_line(self):
        with mock.patch.object(probes.host, "run", wraps=probes.host.run) as ran:
            self.probe(probes.PINNED, "task", acts({"do": "skill", "name": probes.SKILL}))
        lead = f"Load the skill {probes.SKILL} at .fake/skills/{probes.SKILL}/SKILL.md before anything else.\n\n"
        self.assertTrue(ran.call_args.args[1].startswith(lead))

    def test_a_host_that_pages_a_skill_as_long_as_the_round_s_fails_and_one_that_prints_it_whole_passes(self):
        path = f".fake/skills/{probes.SKILL}/SKILL.md"
        for command, passed in ((f"cat {path}", True), (f"sed -n 1,200p {path}", False)):
            with self.subTest(command=command):
                found = probes.probe(fake_adapter(), probes.PINNED, "task", self.tmp / "pro bes",
                                     prompt=acts({"do": "command", "command": command}), timeout=120,
                                     length={"lines": 700, "bytes": 45000},
                                     operator_env={"PATH": f"{self.tool}:/usr/bin:/bin",
                                                   "HTTPS_PROXY": self.upstream.url},
                                     operator_home=self.tmp / "operator", host_paths=[self.tool])
                self.assertEqual(found is None, passed, found)
        written = sorted((self.tmp / "pro bes").glob(f"*/world/{path}"))[-1].read_bytes()
        self.assertGreaterEqual((written.count(b"\n"), len(written)), (700, 45000))


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class LeadFault(Fake):
    def test_the_view_fault_catches_a_view_that_shows_the_lead_line(self):
        setup, entry = self.setup_of(), next(e for e in faults.load() if e["id"] == "view")

        def keeps_lead(value, words, folders):  # the view as it is, except that it keeps the lead line
            start = b"Load the skill " if isinstance(value, bytes) else "Load the skill "
            return value[:0].join(line if line.startswith(start) else TEXT(line, words, folders)
                                  for line in value.splitlines(keepends=True))
        for place in ("message", "log"):
            for seed in (0, 2):
                with self.subTest(place=place, seed=seed), mock.patch.object(view, "text", keeps_lead):
                    outcome = faults.run(entry, setup, seed=seed, place=place)
                    self.assertFalse(outcome["caught"])
                    self.assertIn("the view a grader gets names", outcome["reason"])


TEXT = view.text


if __name__ == "__main__":
    unittest.main()
