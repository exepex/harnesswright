"""The Codex and Claude Code adapters give the harness contract: the command, the action log and the exposure."""

import importlib.util
import json
import unittest
from pathlib import Path

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

    def test_each_adapter_names_its_hosts_memory_places_outside_the_world(self):
        home, world = Path("/h"), Path("/p/w x")
        expected = {CODEX: [".codex/AGENTS.override.md", ".codex/AGENTS.md", ".codex/memories/MEMORY.md",
                            ".codex/memories/memory_summary.md", ".codex/memories/raw_memories.md",
                            "../AGENTS.override.md", "../AGENTS.md"],
                    CLAUDE: [".claude/CLAUDE.md", ".claude/rules/hw-probe.md",
                             ".claude/projects/-p-w-x/memory/MEMORY.md", "../CLAUDE.md", "../CLAUDE.local.md",
                             "../.claude/CLAUDE.md"]}
        for module, places in expected.items():
            with self.subTest(host=module.NAME):
                found = [str(p.relative_to(home)) if p.is_relative_to(home) else f"../{p.relative_to(world.parent)}"
                         for p in module.memory_files(home, world)]
                self.assertEqual(found, places)

    def test_the_command_turns_the_hosts_sandbox_and_bundled_skills_off(self):
        command = CODEX.jail_command("trigger", "/w", None)
        self.assertEqual(command, ["codex", "exec", "--json", "--skip-git-repo-check",
                                   "--dangerously-bypass-approvals-and-sandbox", "-c", "skills.bundled.enabled=false",
                                   "--disable", "view_image", "--disable", "goals", "-c", 'web_search="disabled"',
                                   "--cd", "/w", "-"])
        self.assertEqual(CODEX.jail_command("task", "/w", "m")[-3:], ["--model", "m", "-"])
        command = CLAUDE.jail_command("task", "/w", "m")
        settings = {"disableBundledSkills": True, "skillOverrides": {"design": "off", "doctor": "off"},
                    "enabledPlugins": {"cc-plugin-agents-md@builtin": False, "cc-plugin-telemetry@builtin": False,
                                       "cc-plugin-plugin-authoring@builtin": False}}
        self.assertEqual(command[:command.index("--settings") + 1], [
            "claude", "-p", "--output-format", "stream-json", "--verbose", "--setting-sources", "project",
            "--no-session-persistence", "--dangerously-skip-permissions", "--settings"])
        self.assertEqual(json.loads(command[command.index("--settings") + 1]), settings)
        self.assertEqual(command[command.index("--settings") + 2:], [
            "--tools", "Bash,Read,Write,Edit,Glob,Grep,Skill,Task", "--model", "m"])

    def test_each_adapter_plants_each_host_fault_in_its_own_command(self):
        command = CODEX.jail_command("trigger", "/w", "m")
        self.assertNotIn("skills.bundled.enabled=false", CODEX.PLANTS["bundled skills"](command))
        self.assertEqual(len(CODEX.PLANTS["bundled skills"](command)), len(command) - 2)
        self.assertEqual(CODEX.PLANTS["no commands"](command)[-5:],
                         ["--disable", "shell_tool", "--disable", "unified_exec", "-"])
        command = CLAUDE.jail_command("task", "/w", "m")
        planted = CLAUDE.PLANTS["bundled skills"](command)
        settings = json.loads(planted[planted.index("--settings") + 1])
        self.assertEqual((settings["disableBundledSkills"], "skillOverrides" in settings), (False, False))
        planted = CLAUDE.PLANTS["no commands"](command)
        self.assertEqual(planted[planted.index("--tools") + 1], "Read,Write,Edit,Glob,Grep,Skill,Task")
        for module in (CODEX, CLAUDE):  # a plant changes only a copy
            self.assertEqual(module.jail_command("task", "/w", "m"), module.jail_command("task", "/w", "m"))


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
                                      "aggregated_output": "", "parsed_cmd": [{"type": "read", "path": skill}]}),
                             done(8, {"type": "CommandExecution", "command": ["cat", "SKILL.md"], "exit_code": 0,
                                      "cwd": "file:///w/.agents/skills/my%20skill", "aggregated_output": "",
                                      "parsed_cmd": [{"type": "read", "path": "SKILL.md"}]})])
        self.assertEqual(CODEX.action_log("", self.tmp), [
            host.entry("message", text="On it."),
            host.entry("command", command=f"cat {skill}", exit_code=0, output="x" * 5000),  # kept whole
            host.entry("read", "inferred", path=skill), host.entry("skill", "inferred", name="probe-skill"),
            host.entry("write", path="/w/notes.txt", sha256=host.sha256("hi\n")),
            host.entry("write", path="/w/old", sha256=None), host.entry("agent", task="/root/read_a"),
            host.entry("command", command="ls -a", exit_code=2, output=""),
            {"kind": "failed", "source": "observed", "action": "write: /w/b", "path": "/w/b",
             "reason": "Failed to write file /w/b"},
            host.entry("command", command="cat SKILL.md", exit_code=0, output=""),
            host.entry("read", "inferred", path="/w/.agents/skills/my skill/SKILL.md"),
            host.entry("skill", "inferred", name="my skill")])

    def test_the_exposure_is_every_skill_and_tool_any_thread_was_given(self):
        self.assertIsNone(CODEX.exposure("", self.tmp))
        body = ("## Skills\n### Skill roots\n- `r0` = `/w/.agents/skills`\n### Available skills\n"
                "- probe-skill: Writes a token. (file: r0/probe-skill/SKILL.md)\n- odd: a row in another format\n"
                "  continued\n")
        tools = {"functions": "a", "functions.exec": "b", "collaboration.spawn_agent": "c"}
        described = "Run code.\n### `exec_command`\nRuns.\n### `web__run`"
        nested = {"type": "additional_tools", "tools": [{"type": "namespace", "name": "functions", "tools": [
            {"type": "custom", "name": "exec", "description": described}]}]}
        state = {"host_skills": {"body": body}, "top_level_tools": tools}
        changes = [{"environments": {}}, {"top_level_tools": {"clock.sleep": "x"}}]
        self.session("main", [{"type": "response_item", "payload": nested},
                              {"type": "world_state", "payload": {"state": state}}] +
                     [{"type": "world_state", "payload": {"state": change}} for change in changes])
        # Each later record lists only what changed, so nothing listed earlier is dropped.
        sleep = {"host_skills": {"body": ""}, "top_level_tools": {"functions.wait": "d"}}
        self.session("sub", [{"type": "world_state", "payload": {"state": sleep}}])
        odd = "- odd: a row in another format"  # kept whole, so it can never pass as a declared skill
        self.assertEqual(CODEX.exposure("", self.tmp), {"skills": [odd, "probe-skill"], "tools": [
            "clock.sleep", "collaboration.spawn_agent", "functions.exec", "functions.exec/exec_command",
            "functions.exec/web__run", "functions.wait"]})
        none = {"host_skills": {"includeInstructions": True}, "top_level_tools": {"functions.wait": "d"}}
        self.session("sub", [{"type": "world_state", "payload": {"state": none}}])  # a thread with no skills, live
        self.assertEqual(CODEX.exposure("", self.tmp)["skills"], [odd, "probe-skill"])
        moved = {"host_skills": {"text": "- bundled: x"}, "top_level_tools": {"functions.wait": "d"}}
        self.session("sub", [{"type": "world_state", "payload": {"state": moved}}])
        self.assertIsNone(CODEX.exposure("", self.tmp))  # any other record without a body is no report
        self.session("sub", [{"type": "world_state", "payload": {"state": none}}])
        drifted = {"host_skills": {"body": "## Available skills\n- x: y\n"}, "top_level_tools": {}}
        self.session("sub", [{"type": "world_state", "payload": {"state": drifted}}])
        self.assertEqual(CODEX.exposure("", self.tmp)["skills"], [odd, "- x: y", "probe-skill"])  # any layout counts
        self.session("main", [{"type": "response_item", "payload": {"type": "additional_tools", "tools": [
            {"name": "functions", "tools": [{"name": "exec", "description": "no headings"}]}]}},
            {"type": "world_state", "payload": {"state": state}}])
        self.assertIsNone(CODEX.exposure("", self.tmp))  # an exec that names no nested tool is no report
        self.session("main", [{"type": "response_item", "payload": {"type": "additional_tools", "tools": []}},
                              {"type": "world_state", "payload": {"state": state}}])
        self.assertIsNone(CODEX.exposure("", self.tmp))  # nor is a record that declares no exec
        rooted = {"host_skills": {"body": "### Available skills\n- `r0` = `/x`\n"}, "top_level_tools": {}}
        self.session("sub", [{"type": "world_state", "payload": {"state": rooted}}])
        self.session("main", [{"type": "response_item", "payload": nested},
                              {"type": "world_state", "payload": {"state": state}}])
        self.assertIn("- `r0` = `/x`", CODEX.exposure("", self.tmp)["skills"])  # a root's row only under roots
        self.session("sub", [{"type": "world_state", "payload": {"state": {"top_level_tools": {}}}},
                             {"type": "world_state", "payload": {"state": {"host_skills": {"body": ""}}}}])
        self.assertIsNone(CODEX.exposure("", self.tmp))  # changes only, never one full report
        for state in ({"top_level_tools": {}}, {"host_skills": {"body": ""}}, {"host_skills": "x"}, None,
                      {"host_skills": {"body": ""}, "top_level_tools": {"functions.exec": "b"}}):
            with self.subTest(state=state):  # a thread that does not report all of it is no report, never "nothing"
                self.session("sub", [{"type": "world_state", "payload": {"state": state}}])
                self.assertIsNone(CODEX.exposure("", self.tmp))


class ClaudeCode(unittest.TestCase):
    def stream(self, *events):
        return "".join(json.dumps(event) + "\n" for event in events)

    def test_the_log_pairs_each_tool_call_with_its_result(self):
        uses = [("1", "Read", {"file_path": "/w/a.txt"}), ("2", "Write", {"file_path": "/w/b", "content": "hi"}),
                ("3", "Edit", {"file_path": "/w/c"}), ("4", "Bash", {"command": "make"}), ("5", "Glob", {}),
                ("6", "Skill", {"skill": "probe-skill"}), ("7", "Task", {"description": "judge it"}),
                ("8", "Write", {"file_path": "/w/d", "content": "x"}), ("9", "Read", {"file_path": "/w/gone"}),
                ("10", "Bash", {"command": "printf x"}), ("12", "Bash", {"command": "sleep 9"}),
                ("11", "Read", {"file_path": "/w/.claude/skills/s/SKILL.md"}),
                ("13", "Write", {"file_path": "/w/cut", "content": "x"})]  # no result: the stream was cut
        results = {"4": ("Exit code 2\nboom", True), "8": ("EROFS: read-only file system", True),
                   "9": ("File does not exist.", True), "10": ("Exit code 3 is only output", False),
                   "12": ("Command timed out", True)}
        results = {i: results.get(i, ("ok", False)) for i, _, _ in uses if i != "13"}
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
            host.entry("command", command="printf x", exit_code=0, output="Exit code 3 is only output"),
            host.entry("command", command="sleep 9", exit_code=None, output="Command timed out"),
            host.entry("read", path="/w/.claude/skills/s/SKILL.md"), host.entry("skill", "inferred", name="s"),
            host.entry("blocked", action="WebFetch", reason="the host refused it")])
        self.assertEqual(CLAUDE.exposure(stdout, None), {"skills": ["probe-skill"], "tools": ["Bash", "Read"]})
        self.assertIsNone(CLAUDE.exposure(self.stream({"type": "result"}), None))
        for init in ({"tools": ["Bash"]}, {"skills": []}, {"skills": "s", "tools": []}):
            with self.subTest(init=init):  # a start-up event that does not list both is no report
                stdout = self.stream({"type": "system", "subtype": "init", **init})
                self.assertIsNone(CLAUDE.exposure(stdout, None))


class Tokens(TempCase):
    """Each adapter reads the host's own token counts by model, and reports none when the host reported none."""

    def session(self, name, records):
        path = self.tmp / ".codex" / "sessions" / "2026" / f"rollout-{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")

    def test_codex_counts_each_response_once_under_its_turns_model_sub_agents_and_forks_included(self):
        def turn(turn_id, model):
            return {"type": "turn_context", "payload": {"turn_id": turn_id, "model": model}}

        def used(thread, response, turn_id, usage):
            return {"type": "token_usage_record", "payload": {
                "thread_id": thread, "response_id": response, "turn_id": turn_id, "usage": usage,
                "thread_token_usage": {"input_tokens": 999999}}}  # a running total is never read

        def total(n):  # the running total a forked child inherits and goes on from
            return {"type": "event_msg", "payload": {"type": "token_count", "info": {
                "total_token_usage": {"input_tokens": n}, "last_token_usage": {"input_tokens": n}}}}

        parent = [turn("t1", "model-a"), used("p", "r1", "t1", {"input_tokens": 1000, "cached_input_tokens": 600,
                                                                 "output_tokens": 50}), total(1000)]
        self.session("a", [*parent, used("p", "r3", "t1", {"input_tokens": 500, "cached_input_tokens": 0,
                                                           "output_tokens": 5, "reasoning_output_tokens": 3})])
        # A forked child: the parent's history copied, a usage record copied too, then its own turn on another model.
        self.session("b", [*parent, total(1000), turn("t2", "model-b"),
                           used("c", "r2", "t2", {"input_tokens": 200, "cached_input_tokens": 0,
                                                  "cache_write_input_tokens": 4, "output_tokens": 1}), total(1200)])
        self.session("c", [{"type": "token_usage_record", "payload": {"usage": "not usage"}}])
        self.assertEqual(CODEX.tokens("", self.tmp), {
            "model-a": {"input": 1500, "cache read": 600, "cache write": 0, "output": 55},
            "model-b": {"input": 200, "cache read": 0, "cache write": 4, "output": 1}})
        self.assertIsNone(CODEX.tokens("", self.tmp / "nothing"))

    def test_claude_code_counts_are_its_last_results_for_each_model(self):
        models = {"model-a": {"inputTokens": 5, "outputTokens": 9, "cacheReadInputTokens": 40,
                              "cacheCreationInputTokens": 20},
                  "model-b": {"inputTokens": 1, "outputTokens": 2, "cacheReadInputTokens": 0,
                              "cacheCreationInputTokens": 3}}
        usage = {"input_tokens": 5, "output_tokens": 9, "cache_read_input_tokens": 40,
                 "cache_creation_input_tokens": 20}
        init = {"type": "system", "subtype": "init", "model": "model-a"}
        first = {"type": "result", "usage": {"input_tokens": 999, "output_tokens": 999}}
        last = {"type": "result", "result": "Done.", "usage": usage, "modelUsage": models}
        stdout = "\n".join(json.dumps(event) for event in (init, first, last))
        self.assertEqual(CLAUDE.tokens(stdout, self.tmp), {
            "model-a": {"input": 65, "cache read": 40, "cache write": 20, "output": 9},
            "model-b": {"input": 4, "cache read": 0, "cache write": 3, "output": 2}})
        no_models = "\n".join(json.dumps(event) for event in (init, {**last, "modelUsage": {}}))
        self.assertEqual(CLAUDE.tokens(no_models, self.tmp),
                         {"model-a": {"input": 65, "cache read": 40, "cache write": 20, "output": 9}})
        self.assertIsNone(CLAUDE.tokens(json.dumps({"type": "result", "result": "Done."}), self.tmp))
        self.assertIsNone(CLAUDE.tokens("", self.tmp))


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
