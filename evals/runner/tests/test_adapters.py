"""Tests for the host adapters. They fail when an adapter builds a wrong command."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

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

    def test_task_command_runs_commands_in_the_sandbox_only(self):
        command = CLAUDE.build_command("task", WORKSPACE, None, Path("/tmp/scratch"))
        self.assertEqual(command[8:], [
            "--permission-mode", "acceptEdits", "--settings",
            '{"sandbox": {"enabled": true, "autoAllowBashIfSandboxed": true, "allowUnsandboxedCommands": false}}',
            "--add-dir", "/tmp/scratch"])
        self.assertNotIn("bypassPermissions", command)
        self.assertNotIn("--dangerously-skip-permissions", command)

    def test_trigger_command_gets_no_sandbox_or_scratch(self):
        command = CLAUDE.build_command("trigger", WORKSPACE, None, Path("/tmp/scratch"))
        self.assertNotIn("--settings", command)
        self.assertNotIn("--add-dir", command)

    def test_sandbox_tools_are_required_for_tasks_on_linux(self):
        with mock.patch.object(CLAUDE.shutil, "which", return_value=None):
            self.assertEqual(CLAUDE.missing_requirements("task", "linux"),
                             "the Claude Code sandbox needs bwrap, socat on PATH")
            self.assertIsNone(CLAUDE.missing_requirements("trigger", "linux"))
            self.assertIsNone(CLAUDE.missing_requirements("task", "darwin"))

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
        self.assertIsNone(CLAUDE.failure(ok, 0, False, "task"))
        self.assertEqual(CLAUDE.final_message(ok), "done")
        self.assertIn("error", CLAUDE.failure([{"type": "result", "is_error": True}], 1, False, "task"))
        self.assertEqual(CLAUDE.failure([], 1, False, "task"), "exit code 1")
        self.assertEqual(CLAUDE.failure([], None, True, "trigger"), "timed out")

    def test_timed_out_trigger_run_counts_after_host_acted(self):
        self.assertIsNone(CLAUDE.failure([claude_tool("Skill", {"skill": "demo"})], None, True, "trigger"))

    def test_timed_out_task_run_always_fails(self):
        partial = [{"type": "assistant", "message": {"content": [{"type": "text", "text": "working"}]}}]
        self.assertEqual(CLAUDE.failure(partial, None, True, "task"), "timed out")

    def test_live_refusals_are_reported(self):
        # Shape seen from Claude Code 2.1.314 on 2026-10-30 under acceptEdits without the sandbox.
        result = {"type": "result", "is_error": False, "result": "Neither command ran.", "permission_denials": [
            {"tool_name": "Bash", "tool_use_id": "toolu_1",
             "tool_input": {"command": "python3 t.py", "description": "Run t.py script"}}]}
        self.assertEqual(CLAUDE.refusals([result]), ["Bash: python3 t.py"])
        self.assertEqual(CLAUDE.refusals([{"type": "result", "permission_denials": []}]), [])

    def test_resolved_model_comes_from_init_event(self):
        init = {"type": "system", "subtype": "init", "model": "claude-sonnet-5-5"}
        self.assertEqual(CLAUDE.resolved_model([init]), "claude-sonnet-5-5")
        self.assertIsNone(CLAUDE.resolved_model([]))

    def test_task_profile_names_the_sandbox(self):
        self.assertEqual(CLAUDE.permission_profile("task")["network"], "blocked")
        self.assertEqual(CLAUDE.permission_profile("trigger")["commands"], "refused")


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

    def test_task_command_adds_scratch_as_writable(self):
        command = CODEX.build_command("task", WORKSPACE, "m", Path("/tmp/scratch"))
        self.assertEqual(command[-5:], ["--add-dir", "/tmp/scratch", "--model", "m", "-"])
        self.assertNotIn("--add-dir", CODEX.build_command("trigger", WORKSPACE, None, Path("/tmp/s")))

    def test_codex_needs_nothing_extra_and_refuses_nothing(self):
        self.assertIsNone(CODEX.missing_requirements("task"))
        self.assertEqual(CODEX.refusals([codex_item("command_execution", command="ls")]), [])
        self.assertEqual(CODEX.permission_profile("task")["setting"], "sandbox workspace-write")
        self.assertIsNone(CODEX.resolved_model([{"type": "thread.started", "thread_id": "t"}]))

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

    def test_listing_whose_output_shows_skill_does_not_trigger(self):
        event = codex_item("command_execution", command="bash -lc 'find . -name SKILL.md'",
                           aggregated_output="./.agents/skills/demo/SKILL.md\n", status="completed")
        self.assertFalse(CODEX.skill_triggered([event], "demo"))

    def test_listing_the_skill_path_itself_does_not_trigger(self):
        event = codex_item("command_execution", command="ls -l .agents/skills/demo/SKILL.md")
        self.assertFalse(CODEX.skill_triggered([event], "demo"))

    def test_any_reading_command_triggers(self):
        for command in ("bash -lc 'rg -n \"Steps\" .agents/skills/demo/SKILL.md'",
                        "/bin/bash -lc \"grep -c x ./.agents/skills/demo/SKILL.md\"",
                        "bash -lc 'python3 -c \"print(open(\\\".agents/skills/demo/SKILL.md\\\").read())\"'",
                        "bash -lc 'ls .agents/skills && cat .agents/skills/demo/SKILL.md | head -50'",
                        "bash -lc 'while read l; do echo $l; done < .agents/skills/demo/SKILL.md'",
                        "LC_ALL=C wc -l .agents/skills/demo/SKILL.md"):
            event = codex_item("command_execution", command=command)
            self.assertTrue(CODEX.skill_triggered([event], "demo"), command)

    def test_path_only_commands_do_not_trigger(self):
        for command in ("bash -lc 'ls .agents/skills/demo/SKILL.md && echo found'",
                        "bash -lc 'test -f .agents/skills/demo/SKILL.md'",
                        "stat .agents/skills/demo/SKILL.md"):
            event = codex_item("command_execution", command=command)
            self.assertFalse(CODEX.skill_triggered([event], "demo"), command)

    def test_tool_call_reading_skill_triggers(self):
        event = codex_item("mcp_tool_call", tool="read_file", arguments={"path": ".agents/skills/demo/SKILL.md"},
                           result="name: demo")
        self.assertTrue(CODEX.skill_triggered([event], "demo"))

    def test_tool_result_mentioning_skill_does_not_trigger(self):
        event = codex_item("mcp_tool_call", tool="list", arguments={"path": "."},
                           result=".agents/skills/demo/SKILL.md")
        self.assertFalse(CODEX.skill_triggered([event], "demo"))

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
        self.assertIsNone(CODEX.failure(done, 0, False, "task"))
        failed = [{"type": "turn.failed", "error": {"message": "unauthorized"}}]
        self.assertEqual(CODEX.failure(failed, 1, False, "task"), "host reported turn.failed: unauthorized")
        self.assertEqual(CODEX.failure([], 0, False, "task"), "no turn.completed event")
        self.assertEqual(CODEX.failure([], 2, False, "task"), "exit code 2")

    def test_timeouts_fail_tasks_but_not_acted_triggers(self):
        partial = [codex_item("agent_message", text="working")]
        self.assertEqual(CODEX.failure(partial, None, True, "task"), "timed out")
        self.assertIsNone(CODEX.failure(partial, None, True, "trigger"))
        self.assertEqual(CODEX.failure([], None, True, "trigger"), "timed out")

    def test_parse_reads_documented_example(self):
        line = json.dumps({"type": "item.started", "item": {"id": "item_1", "type": "command_execution",
                                                             "command": "bash -lc ls", "status": "in_progress"}})
        self.assertEqual(CODEX.parse_events(line + "\n")[0]["item"]["command"], "bash -lc ls")


if __name__ == "__main__":
    unittest.main()
