"""The Codex and Claude Code adapters give the harness contract: the command, the action log and the exposure."""

import importlib.util
import json
import unittest

from helpers import TempCase

import contain
import host
import manifest
from cases import REPO


def adapter(name):
    spec = importlib.util.spec_from_file_location(f"adapter_{name.replace('-', '_')}",
                                                  REPO / "adapters" / name / "adapter.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CODEX, CLAUDE = adapter("codex"), adapter("claude-code")


def done(started, item):
    return {"type": "event_msg", "payload": {"type": "item_completed", "started_at_ms": started, "item": item}}


class Contract(unittest.TestCase):
    def test_both_adapters_give_the_whole_contract(self):
        for module in (CODEX, CLAUDE):
            with self.subTest(host=module.NAME):
                host.check_adapter(module)

    def test_the_command_turns_the_hosts_sandbox_and_bundled_skills_off(self):
        command = CODEX.jail_command("trigger", "/w", None)
        self.assertEqual(command, ["codex", "exec", "--json", "--skip-git-repo-check",
                                   "--dangerously-bypass-approvals-and-sandbox", "-c", "skills.bundled.enabled=false",
                                   "--cd", "/w", "-"])
        self.assertEqual(CODEX.jail_command("task", "/w", "m")[-3:], ["--model", "m", "-"])
        command = CLAUDE.jail_command("task", "/w", None)
        self.assertIn("--dangerously-skip-permissions", command)
        self.assertEqual(command[command.index("--tools") + 1], ",".join(CLAUDE.TOOLS))
        settings = json.loads(command[command.index("--settings") + 1])
        self.assertIs(settings["disableBundledSkills"], True)
        self.assertNotIn("--permission-mode", command)


class Codex(TempCase):
    def session(self, name, records):
        folder = self.tmp / ".codex" / "sessions" / "2026" / "10" / "31"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"rollout-{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records) + "not json\n")

    def test_the_log_reads_every_thread_from_the_session_files_in_order(self):
        skill = "/w/.agents/skills/probe-skill/SKILL.md"
        self.session("main", [
            done(1, {"type": "AgentMessage", "content": [{"type": "Text", "text": "On it."}]}),
            done(2, {"type": "CommandExecution", "command": ["/bin/bash", "-lc", f"cat {skill}"], "exit_code": 0,
                     "aggregated_output": "x" * 5000, "parsed_cmd": [{"type": "read", "path": skill}]}),
            done(3, {"type": "FileChange", "status": "completed",
                     "changes": {"/w/notes.txt": {"type": "add", "content": "hi\n"}, "/w/old": {"type": "delete"}}}),
            done(4, {"type": "SubAgentActivity", "kind": "started", "agent_path": "/root/read_a"}),
            done(6, {"type": "FileChange", "status": "failed", "stderr": "Failed to write file /w/b\n",
                     "changes": {"/w/b": {"type": "add", "content": "x"}}}),
            done(7, {"type": "UserMessage", "content": []})])
        self.session("sub", [done(5, {"type": "CommandExecution", "command": ["ls", "-a"], "exit_code": 2,
                                      "aggregated_output": "", "parsed_cmd": []})])
        self.assertEqual(CODEX.action_log("", self.tmp), [
            host.entry("message", text="On it."),
            host.entry("command", command=f"cat {skill}", exit_code=0, output="x" * 4000),
            host.entry("read", "inferred", path=skill), host.entry("skill", "inferred", name="probe-skill"),
            host.entry("write", path="/w/notes.txt", sha256=host.sha256("hi\n")),
            host.entry("write", path="/w/old", sha256=None), host.entry("agent", task="/root/read_a"),
            host.entry("command", command="ls -a", exit_code=2, output=""),
            {"kind": "failed", "source": "observed", "action": "write: /w/b", "path": "/w/b",
             "reason": "Failed to write file /w/b"}])

    def test_the_exposure_is_every_skill_and_tool_any_thread_was_given(self):
        self.assertIsNone(CODEX.exposure("", self.tmp))
        body = ("## Skills\n### Available skills\n- probe-skill: Writes a token. (file: r0/probe-skill/SKILL.md)\n"
                "- not a row\n")
        tools = {"functions": "a", "functions.exec": "b", "collaboration.spawn_agent": "c"}
        self.session("main", [{"type": "world_state", "payload": {"state": {"host_skills": {"body": body},
                                                                            "top_level_tools": tools}}}])
        sleep = {"top_level_tools": {"clock.sleep": "d"}}
        self.session("sub", [{"type": "world_state", "payload": {"state": sleep}}])
        self.assertEqual(CODEX.exposure("", self.tmp), {"skills": ["probe-skill"], "tools": [
            "clock.sleep", "collaboration.spawn_agent", "functions.exec"]})


class ClaudeCode(unittest.TestCase):
    def stream(self, *events):
        return "".join(json.dumps(event) + "\n" for event in events)

    def test_the_log_pairs_each_tool_call_with_its_result(self):
        uses = [("1", "Read", {"file_path": "/w/a.txt"}), ("2", "Write", {"file_path": "/w/b", "content": "hi"}),
                ("3", "Edit", {"file_path": "/w/c"}), ("4", "Bash", {"command": "make"}), ("5", "Glob", {}),
                ("6", "Skill", {"skill": "probe-skill"}), ("7", "Task", {"description": "judge it"}),
                ("8", "Write", {"file_path": "/w/d", "content": "x"}), ("9", "Read", {"file_path": "/w/gone"})]
        results = {"4": ("Exit code 2\nboom", True), "8": ("EROFS: read-only file system", True),
                   "9": ("File does not exist.", True)}
        stdout = self.stream(
            {"type": "system", "subtype": "init", "skills": ["probe-skill"], "tools": ["Bash", "Read"]},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "On it."}] + [
                {"type": "tool_use", "id": i, "name": n, "input": a} for i, n, a in uses]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": i, "content": [{"type": "text", "text": t}], "is_error": e}
                for i, (t, e) in results.items()]}},
            {"type": "result", "result": "Done.", "permission_denials": [{"tool_name": "WebFetch"}]})
        self.assertEqual(CLAUDE.action_log(stdout, None), [
            host.entry("message", text="On it."), host.entry("read", path="/w/a.txt"),
            host.entry("write", path="/w/b", sha256=host.sha256("hi")), host.entry("write", path="/w/c", sha256=None),
            host.entry("command", command="make", exit_code=2, output="Exit code 2\nboom"),
            host.entry("skill", name="probe-skill"), host.entry("agent", task="judge it"),
            {"kind": "failed", "source": "observed", "action": "Write: /w/d", "path": "/w/d",
             "reason": "EROFS: read-only file system"},
            host.entry("blocked", action="WebFetch", reason="the host refused it")])
        self.assertEqual(CLAUDE.exposure(stdout, None), {"skills": ["probe-skill"], "tools": ["Bash", "Read"]})
        self.assertIsNone(CLAUDE.exposure(self.stream({"type": "result"}), None))


class RunEnv(TempCase):
    def test_an_adapters_fixed_variables_are_set_and_never_taken_from_the_operator(self):
        world = self.tmp / "world"
        world.mkdir()
        run = contain.Containment(CLAUDE, "task", world, manifest.manifest(world), root=self.tmp / "run",
                                  operator_env={"PATH": "/usr/bin:/bin", "IS_SANDBOX": "0", "CLAUDE_X": "1"},
                                  operator_home=self.tmp / "operator")
        self.assertEqual(run.env["IS_SANDBOX"], "1")
        self.assertNotIn("CLAUDE_X", run.env)


if __name__ == "__main__":
    unittest.main()
