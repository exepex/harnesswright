"""Pinned load (doc 12, Proven use): the adapter's lead line, the runs that start with it, the manifest that pins, the
view that never shows it, and the probe that proves a pin loads before any real run."""

import types
import unittest
from unittest import mock

from helpers import TempCase
from test_host import fake_adapter
from test_probes import JAIL, ProbeCase, acts
from test_runs import DRIFT, Round

import host
import probes
import rounds
import runs
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

    def test_the_probe_prompt_starts_with_the_lead_line_for_the_small_probe_skill(self):
        with mock.patch.object(probes.host, "run", wraps=probes.host.run) as ran:
            self.probe(probes.PINNED, "task", acts({"do": "skill", "name": probes.SKILL}))
        lead = f"Load the skill {probes.SKILL} at .fake/skills/{probes.SKILL}/SKILL.md before anything else.\n\n"
        self.assertTrue(ran.call_args.args[1].startswith(lead))
        self.assertLess(len(probes.skill_text({"discovery": probes.new_token()})), 400)


if __name__ == "__main__":
    unittest.main()
