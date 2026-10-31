"""The adapters' harness contract: each host is configured to the power table, with host extras turned off, and
its events become the same action log."""

import json
import unittest

import helpers  # noqa: F401  (puts the harness on the path)
import hosts
import evidence

CLAUDE = hosts.load("claude-code")
CODEX = hosts.load("codex")


class Commands(unittest.TestCase):
    def test_claude_code_has_only_the_table_tools_and_no_bundled_skills_or_plugins(self):
        trigger = CLAUDE.command("trigger", "/w")
        task = CLAUDE.command("task", "/w", scratch="/s", deny=("python3",))
        self.assertEqual(trigger[trigger.index("--tools") + 1], "Bash,Read,Glob,Grep,Skill")
        self.assertEqual(task[task.index("--tools") + 1], "Bash,Read,Glob,Grep,Skill,Edit,Write")
        self.assertNotIn("--add-dir", trigger)
        trigger_settings = json.loads(trigger[trigger.index("--settings") + 1])
        self.assertEqual(trigger_settings["sandbox"]["filesystem"]["denyWrite"], ["~", "/tmp"])
        self.assertEqual(task[task.index("--add-dir") + 1], "/s")
        settings = json.loads(task[task.index("--settings") + 1])
        self.assertTrue(settings["disableBundledSkills"])
        self.assertFalse(any(settings["enabledPlugins"].values()))
        self.assertFalse(settings["sandbox"]["allowUnsandboxedCommands"])
        self.assertEqual(settings["permissions"]["deny"], ["Bash(python3:*)"])
        self.assertIn("--strict-mcp-config", task)
        self.assertEqual(CLAUDE.SEALED_ENV, {"CLAUDE_CODE_DISABLE_BUNDLED_SKILLS": "1"})

    def test_codex_turns_off_bundled_skills_and_extras_and_leaves_tmp_out(self):
        trigger = CODEX.command("trigger", "/w")
        task = CODEX.command("task", "/w", scratch="/s")
        self.assertEqual(trigger[trigger.index("--sandbox") + 1], "read-only")
        self.assertEqual(task[task.index("--sandbox") + 1], "workspace-write")
        for args in (trigger, task):
            self.assertIn("skills.bundled.enabled=false", args)
            self.assertIn("--strict-config", args)
            disabled = {args[i + 1] for i, a in enumerate(args) if a == "--disable"}
            self.assertLessEqual({"multi_agent", "plugins", "memories", "apps", "browser_use"}, disabled)
        self.assertIn("sandbox_workspace_write.exclude_slash_tmp=true", task)
        self.assertIn("sandbox_workspace_write.exclude_tmpdir_env_var=true", task)
        self.assertEqual(task[task.index("--add-dir") + 1], "/s")


class ActionLogs(unittest.TestCase):
    def test_codex_policy_refusals_come_from_stderr(self):
        stderr = ('ERROR codex_core::tools::router: error=exec_command failed: CreateProcess { message: '
                  '"Rejected(\\"`/bin/bash -lc \'python3 -c \\\\\\"print(42)\\\\\\"\'` rejected: policy forbids '
                  'commands starting with `python3`\\")" }')
        log = CODEX.actions([], stderr)
        self.assertEqual([e["kind"] for e in log], ["blocked"])
        self.assertIn("policy forbids", log[0]["reason"])

    def test_codex_rules_file_for_denied_commands(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as home:
            written = CODEX.prepare_home(home, ["python3", "go test"])
            rules = (Path(home) / written[0]).read_text()
        self.assertIn('prefix_rule(pattern=["python3"], decision="forbidden")', rules)
        self.assertIn('prefix_rule(pattern=["go", "test"], decision="forbidden")', rules)

    def test_claude_code_events_become_observed_entries(self):
        events = [
            {"type": "system", "subtype": "init", "skills": ["design", "haiku-writer"], "plugins": []},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "1", "name": "Skill", "input": {"skill": "haiku-writer"}},
                {"type": "tool_use", "id": "2", "name": "Read", "input": {"file_path": "/w/a.md"}},
                {"type": "tool_use", "id": "3", "name": "Bash", "input": {"command": "go test ./..."}},
                {"type": "tool_use", "id": "4", "name": "Bash", "input": {"command": "rm -rf /"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "1", "content": "Launching skill", "is_error": False},
                {"type": "tool_result", "tool_use_id": "2", "content": "# Notes", "is_error": False},
                {"type": "tool_result", "tool_use_id": "3", "content": "ok  notes 0.1s", "is_error": False},
                {"type": "tool_result", "tool_use_id": "4", "content": "This command requires approval",
                 "is_error": True}]}},
            {"type": "result", "permission_denials": [{"tool_use_id": "4", "tool_name": "Bash",
                                                       "tool_input": {"command": "rm -rf /"}}]}]
        log = CLAUDE.actions(events)
        self.assertEqual([e["kind"] for e in log], ["skill_load", "read", "command", "blocked"])
        self.assertTrue(all(e["source"] == "observed" for e in log))
        self.assertEqual(log[2]["output"], "ok  notes 0.1s")
        self.assertEqual(CLAUDE.exposed_skills(events, "/h", "/w"), ["design", "haiku-writer"])

    def test_a_claude_code_call_without_a_result_has_no_outcome(self):
        events = [{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "1", "name": "Bash", "input": {"command": "go test ./..."}},
            {"type": "tool_use", "id": "2", "name": "Write", "input": {"file_path": "/w/a.md"}}]}}]
        log = CLAUDE.actions(events)
        self.assertEqual([(e["source"], e.get("exit", e.get("ok"))) for e in log], [("inferred", None)] * 2)
        self.assertEqual(evidence.decidable(log), [])


if __name__ == "__main__":
    unittest.main()
