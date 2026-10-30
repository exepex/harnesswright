"""Tests for the host adapters. They fail when an adapter builds a wrong command."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402

CLAUDE = core.load_adapter("claude-code")
CODEX = core.load_adapter("codex")
WORKSPACE = Path("/tmp/hw-eval-test")


def claude_tool(name, tool_input):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]}}


def codex_item(item_type, **fields):
    return {"type": "item.completed", "item": {"id": "item_1", "type": item_type, **fields}}


class ClaudeCodeCommandTest(unittest.TestCase):
    def test_trigger_command_is_exact(self):
        self.assertEqual(CLAUDE.build_command("trigger", WORKSPACE, None),
                         ["claude", "-p", "--output-format", "stream-json", "--verbose",
                          "--setting-sources", "project", "--no-session-persistence"])

    def test_task_command_allows_edits_only(self):
        command = CLAUDE.build_command("task", WORKSPACE, None)
        self.assertEqual(command[-2:], ["--permission-mode", "acceptEdits"])
        self.assertNotIn("bypassPermissions", command)
        self.assertNotIn("--dangerously-skip-permissions", command)

    def test_model_is_passed_through(self):
        command = CLAUDE.build_command("trigger", WORKSPACE, "some-model")
        self.assertEqual(command[-2:], ["--model", "some-model"])

    def test_prompt_is_not_in_argv(self):
        self.assertNotIn("-", CLAUDE.build_command("trigger", WORKSPACE, None))

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            CLAUDE.build_command("judge", WORKSPACE, None)

    def test_skill_is_installed_in_project_skills(self):
        self.assertEqual(CLAUDE.skill_dir(WORKSPACE, "demo"), WORKSPACE / ".claude/skills/demo")

    def test_environment_drops_session_marker_only(self):
        self.assertEqual(CLAUDE.environment({"CLAUDECODE": "1", "PATH": "/bin"}), {"PATH": "/bin"})


class ClaudeCodeEventsTest(unittest.TestCase):
    def test_skill_tool_with_name_triggers(self):
        self.assertTrue(CLAUDE.skill_triggered([claude_tool("Skill", {"skill": "demo"})], "demo"))

    def test_other_skill_does_not_trigger(self):
        self.assertFalse(CLAUDE.skill_triggered([claude_tool("Skill", {"skill": "demo-two"})], "demo"))

    def test_reading_skill_file_triggers(self):
        event = claude_tool("Read", {"file_path": "/w/.claude/skills/demo/SKILL.md"})
        self.assertTrue(CLAUDE.skill_triggered([event], "demo"))

    def test_text_mentioning_skill_does_not_trigger(self):
        event = {"type": "assistant", "message": {"content": [{"type": "text", "text": "skills/demo/SKILL.md"}]}}
        self.assertFalse(CLAUDE.skill_triggered([event], "demo"))

    def test_parse_skips_non_json_lines(self):
        self.assertEqual(CLAUDE.parse_events('noise\n{"type": "result"}\n[1]\n'), [{"type": "result"}])

    def test_failure_cases(self):
        ok = [{"type": "result", "is_error": False, "result": "done"}]
        self.assertIsNone(CLAUDE.failure(ok, 0, False))
        self.assertEqual(CLAUDE.final_message(ok), "done")
        self.assertIn("error", CLAUDE.failure([{"type": "result", "is_error": True}], 1, False))
        self.assertEqual(CLAUDE.failure([], 1, False), "exit code 1")
        self.assertEqual(CLAUDE.failure([], None, True), "timed out with no output")
        self.assertIsNone(CLAUDE.failure([claude_tool("Skill", {"skill": "demo"})], None, True))


class CodexCommandTest(unittest.TestCase):
    def test_trigger_command_is_exact(self):
        self.assertEqual(CODEX.build_command("trigger", WORKSPACE, None),
                         ["codex", "exec", "--json", "--ephemeral", "--skip-git-repo-check",
                          "--sandbox", "read-only", "--cd", str(WORKSPACE), "-"])

    def test_task_command_writes_only_in_workspace(self):
        command = CODEX.build_command("task", WORKSPACE, None)
        self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")
        self.assertNotIn("danger-full-access", command)
        self.assertNotIn("--full-auto", command)

    def test_prompt_comes_from_stdin_last(self):
        self.assertEqual(CODEX.build_command("task", WORKSPACE, "some-model")[-1], "-")

    def test_model_is_passed_before_stdin_marker(self):
        command = CODEX.build_command("trigger", WORKSPACE, "some-model")
        self.assertEqual(command[-3:], ["--model", "some-model", "-"])

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            CODEX.build_command("judge", WORKSPACE, None)

    def test_skill_is_installed_in_agents_skills(self):
        self.assertEqual(CODEX.skill_dir(WORKSPACE, "demo"), WORKSPACE / ".agents/skills/demo")


class CodexEventsTest(unittest.TestCase):
    def test_command_reading_skill_triggers(self):
        event = codex_item("command_execution", command="bash -lc 'sed -n 1,200p .agents/skills/demo/SKILL.md'")
        self.assertTrue(CODEX.skill_triggered([event], "demo"))

    def test_message_mentioning_skill_does_not_trigger(self):
        event = codex_item("agent_message", text="see .agents/skills/demo/SKILL.md")
        self.assertFalse(CODEX.skill_triggered([event], "demo"))

    def test_other_skill_does_not_trigger(self):
        event = codex_item("command_execution", command="cat .agents/skills/demo-two/SKILL.md")
        self.assertFalse(CODEX.skill_triggered([event], "demo"))

    def test_final_message_is_last_agent_message(self):
        events = [codex_item("agent_message", text="first"), codex_item("agent_message", text="last")]
        self.assertEqual(CODEX.final_message(events), "last")

    def test_failure_cases(self):
        done = [{"type": "turn.completed", "usage": {}}]
        self.assertIsNone(CODEX.failure(done, 0, False))
        failed = [{"type": "turn.failed", "error": {"message": "unauthorized"}}]
        self.assertEqual(CODEX.failure(failed, 1, False), "host reported turn.failed: unauthorized")
        self.assertEqual(CODEX.failure([], 0, False), "no turn.completed event")
        self.assertEqual(CODEX.failure([], 2, False), "exit code 2")

    def test_parse_reads_documented_example(self):
        line = json.dumps({"type": "item.started", "item": {"id": "item_1", "type": "command_execution",
                                                             "command": "bash -lc ls", "status": "in_progress"}})
        self.assertEqual(CODEX.parse_events(line + "\n")[0]["item"]["command"], "bash -lc ls")


if __name__ == "__main__":
    unittest.main()
