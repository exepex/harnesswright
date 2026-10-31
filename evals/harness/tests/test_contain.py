"""Containment: the visibility audit runs in the jail before the host and fails on anything outside the run's
allowed set; a run cannot reach planted copies, canaries, session values or credentials."""

import json
import shutil
import unittest

from helpers import SKILL_MD, TempCase, needs_jail

import contain
import evidence
import hostrun
from cases import tree, tree_hash


class ContainmentFaults(TempCase):
    def box(self, adapter, mode="task", **options):
        world = self.tmp / "run" / "world"
        world.mkdir(parents=True, exist_ok=True)
        (world / "README.md").write_text("Notes app.\n")
        options.setdefault("operator_env", self.operator_env())
        options.setdefault("operator_home", self.tmp / "operator-home")
        return contain.Containment(adapter, self.tmp / "run", mode, world, **options)

    def plan(self, *actions, final="done"):
        return json.dumps({"actions": list(actions), "final": final})

    @needs_jail
    def test_a_sealed_run_passes_the_audit_in_both_modes(self):
        adapter = self.fake_adapter()
        for mode in ("task", "trigger"):
            with self.subTest(mode):
                shutil.rmtree(self.tmp / "run", ignore_errors=True)
                run = hostrun.run(adapter, self.box(adapter, mode), self.plan({"run": "ls /"}))
                self.assertIsNone(run.failure)
                self.assertEqual(run.audit["problems"], [])

    @needs_jail
    def test_hf01_skill_copy_and_canary_outside_the_world(self):
        adapter = self.fake_adapter()
        outside = self.tmp / "outside"
        (outside / "skills" / "haiku-writer").mkdir(parents=True)
        (outside / "skills" / "haiku-writer" / "SKILL.md").write_text(SKILL_MD)
        canaries = contain.plant_canaries([outside, self.tmp / "operator-home"])
        box = self.box(adapter, canaries=canaries, forbidden=[str(outside)])
        paths = [str(outside / "skills" / "haiku-writer" / "SKILL.md")] + list(canaries.values())
        run = hostrun.run(adapter, box, self.plan(*[{"read": p} for p in paths],
                                                  {"run": f"cat {' '.join(paths)}; ls {outside}"}))
        reads = [e for e in run.actions if e["kind"] == "read"]
        self.assertEqual([e["ok"] for e in reads], [False] * len(paths))
        record = json.dumps(run.record())
        self.assertEqual(evidence.tokens_in(record, canaries), [])
        self.assertNotIn("Count the syllables", record)
        # The negative control: a jail that mounts the planted folder fails the audit, so no run starts.
        leaky = self.box(adapter, canaries=canaries, forbidden=[str(outside)], host_paths=[str(outside)])
        with self.assertRaisesRegex(contain.ContainmentError, "canary"):
            leaky.audit(adapter.CLI)

    @needs_jail
    def test_hf03_operator_environment(self):
        adapter = self.fake_adapter()
        secret = "fake-key-SECRET-0123456789"
        env = self.operator_env(FAKE_HOST_KEY=secret, CLAUDECODE="1", CLAUDE_CODE_SESSION_ID="s-1",
                                CLAUDE_COWORK_MEMORY_PATH_OVERRIDE="/memory", CODEX_HOME="/codex")
        box = self.box(adapter, operator_env=env)
        for key in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_COWORK_MEMORY_PATH_OVERRIDE", "CODEX_HOME"):
            self.assertNotIn(key, box.env)
        run = hostrun.run(adapter, box, self.plan({"env": True}, {"run": "env"}, final=None))
        self.assertIn(secret, json.dumps(run.record()))
        (box.world / "notes.txt").write_text(f"key={secret}\n")
        bundle = self.tmp / "bundle"
        evidence.write_bundle(bundle, run.record(), box.world, box.secrets(), [])
        written = (bundle / "bundle.json").read_text() + (bundle / "files" / "notes.txt").read_text()
        self.assertNotIn(secret, written)
        self.assertIn(evidence.REDACTED, written)
        self.assertNotIn("CLAUDE_CODE_SESSION_ID", written)

    @needs_jail
    def test_hf10_world_swapped(self):
        adapter = self.fake_adapter()
        box = self.box(adapter)
        box.world_sha256 = tree_hash(tree(box.world, skip=(".git",)))
        box.audit(adapter.CLI)
        (box.world / "hint.md").write_text("Use the haiku skill.\n")
        with self.assertRaisesRegex(contain.ContainmentError, "not the built arm"):
            box.audit(adapter.CLI)

    @needs_jail
    def test_masked_folders_are_empty_and_trigger_worlds_are_read_only(self):
        adapter = self.fake_adapter()
        box = self.box(adapter, "trigger", masks=["/usr/share/doc"])
        run = hostrun.run(adapter, box, self.plan({"run": "ls -A /usr/share/doc | wc -l"},
                                                  {"write": [str(box.world / "x.txt"), "x"]}))
        command = next(e for e in run.actions if e["kind"] == "command")
        self.assertEqual(command["output"].strip(), "0")
        self.assertFalse(next(e for e in run.actions if e["kind"] == "write")["ok"])

    @needs_jail
    def test_the_audit_sees_the_host_install_the_host_gets(self):
        adapter = self.fake_adapter()
        install = __import__("pathlib").Path(adapter.CLI).parents[1]
        canaries = contain.plant_canaries([install])
        with self.assertRaisesRegex(contain.ContainmentError, "canary"):
            self.box(adapter, canaries=canaries).audit(adapter.CLI)

    def test_nothing_of_the_repository_is_mounted(self):
        adapter = self.fake_adapter()
        box = self.box(adapter, host_paths=[str(contain.REPO / "skills")])
        with self.assertRaisesRegex(contain.ContainmentError, "repository"):
            box.mounts(adapter.CLI)

    @needs_jail
    def test_the_audit_names_variables_outside_the_allow_list(self):
        adapter = self.fake_adapter()
        box = self.box(adapter)
        box.env["SESSION_TOKEN"] = "leaked"
        with self.assertRaisesRegex(contain.ContainmentError, "SESSION_TOKEN"):
            box.audit(adapter.CLI)


if __name__ == "__main__":
    unittest.main()
