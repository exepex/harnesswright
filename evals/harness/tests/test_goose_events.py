"""The goose adapter's event readers, on real runs captured through `host.run` in the jail and the gate (folder
`goose/`, README there): the action log and the token counts from goose's session store, and the exposure only when
every model response has its request logged."""

import hashlib
import json
import shutil
import sqlite3
import unittest
from pathlib import Path

from helpers import TempCase
from test_adapters import adapter

import host

GOOSE = adapter("goose")
FIXTURES = Path(__file__).resolve().parent / "goose"
STORE = Path(".local") / "share" / "goose" / "sessions"
LOGS = Path(".local") / "state" / "goose" / "logs"
# The store's tables as goose 1.59.1 makes them, cut to the columns the adapter reads.
SCHEMA = ("CREATE TABLE sessions (id TEXT PRIMARY KEY, working_dir TEXT NOT NULL);"
          "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL,"
          " content_json TEXT NOT NULL);"
          "CREATE TABLE usage_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, model TEXT, input_tokens INTEGER,"
          " cache_read_tokens INTEGER, cache_write_tokens INTEGER, output_tokens INTEGER);")


def write_store(home, store):
    """A session store in `home` holding `store` ({"sessions", "messages", "usage"}, rows as the fixtures keep them)."""
    folder = Path(home) / STORE
    folder.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(folder / "sessions.db")
    db.executescript(SCHEMA)
    db.executemany("INSERT INTO sessions VALUES (?, ?)", store["sessions"])
    db.executemany("INSERT INTO messages (session_id, role, content_json) VALUES (?, ?, ?)", store["messages"])
    db.executemany("INSERT INTO usage_ledger (model, input_tokens, cache_read_tokens, cache_write_tokens, "
                   "output_tokens) VALUES (?, ?, ?, ?, ?)", store["usage"])
    db.commit()
    db.close()


class Captured(TempCase):
    def run_of(self, name):
        """(stdout, home, store) of the captured run `name`, its home rebuilt in the test's folder."""
        store = json.loads((FIXTURES / name / "store.json").read_text())
        home = self.tmp / name
        write_store(home, store)
        shutil.copytree(FIXTURES / name / "logs", home / LOGS)
        return (FIXTURES / name / "stdout.jsonl").read_text(), home, store

    def kinds(self, log):
        return [item["kind"] for item in log]

    def test_a_full_run_logs_each_action_in_order_sub_agent_included(self):
        stdout, home, _ = self.run_of("full")
        log = GOOSE.action_log(stdout, home)
        host.check_log([item for item in log if item["kind"] != "failed"], ["tidy"])
        self.assertEqual(self.kinds(log), ["skill", "command", "command", "write", "message", "command", "command",
                                           "message", "write", "message", "read", "agent", "command", "message",
                                           "message", "message"])
        commands = [(item["command"], item["exit_code"]) for item in log if item["kind"] == "command"]
        self.assertEqual(commands, [("cat notes.txt", 0), ("od -c notes.txt", 0), ("wc -l tidy.txt", 0),
                                    ("cat missing.txt", 1), ("head -1 README.md", 0)])  # the last by the sub-agent
        self.assertIn("No such file", log[6]["output"])
        write, edit = [item for item in log if item["kind"] == "write"]
        self.assertEqual(write, {"kind": "write", "source": "observed", "path": "/run/project/tidy.txt",
                                 "sha256": hashlib.sha256(b"apple\nfig\npear\n").hexdigest()})
        self.assertIsNone(edit["sha256"])  # an edit reports no content
        self.assertEqual(log[10]["path"], "/run/project")
        self.assertTrue(log[-1]["text"].startswith("Tidied notes.txt"))  # the main session's last answer
        self.assertIsNone(GOOSE.run_failure(stdout, 0, False))

    def test_the_token_counts_are_goose_s_own_totals_by_model(self):
        for name in ("full", "parallel", "blocked"):
            stdout, home, _ = self.run_of(name)
            complete = [json.loads(line) for line in stdout.splitlines() if '"complete"' in line][-1]
            self.assertEqual(GOOSE.tokens(stdout, home), {"model-a": {
                "input": complete["input_tokens"], "cache read": complete["cache_read_input_tokens"],
                "cache write": complete["cache_write_input_tokens"], "output": complete["output_tokens"]}})
            host.check_tokens(GOOSE.tokens(stdout, home))

    def test_parallel_sub_agents_each_log_their_actions_and_lose_no_request(self):
        stdout, home, _ = self.run_of("parallel")
        log = GOOSE.action_log(stdout, home)
        self.assertEqual(self.kinds(log)[:4], ["agent", "agent", "command", "command"])
        exposure = GOOSE.exposure(stdout, home)
        self.assertIn("recipe__final_output", exposure["tools"])  # each sub-agent's own tool
        host.check_exposure(GOOSE, exposure, ["tidy"])

    def test_a_write_the_jail_refused_is_reported_as_failed(self):
        stdout, home, _ = self.run_of("blocked")
        failed = GOOSE.action_log(stdout, home)[0]
        self.assertEqual((failed["kind"], failed["path"]), ("failed", "/run/project/hello.txt"))
        self.assertIn("Read-only file system", failed["reason"])

    def test_a_failed_run_reports_its_error_and_no_tokens(self):
        stdout, home, _ = self.run_of("error")
        self.assertTrue(GOOSE.run_failure(stdout, 1, False).startswith("host reported error: "))
        self.assertEqual(GOOSE.action_log(stdout, home), [])
        self.assertIsNone(GOOSE.tokens(stdout, home))

    def test_a_lost_or_extra_request_log_leaves_no_report(self):
        stdout, home, _ = self.run_of("full")
        self.assertIsNotNone(GOOSE.exposure(stdout, home))
        logs = sorted((home / LOGS).iterdir())
        shutil.copyfile(logs[0], home / LOGS / "llm_request.extra.jsonl")
        self.assertIsNone(GOOSE.exposure(stdout, home))
        for path in logs[:2]:
            path.unlink()
        self.assertIsNone(GOOSE.exposure(stdout, home))

    def test_no_store_or_one_in_another_form_reads_nothing_and_leaves_no_report(self):
        stdout, home, store = self.run_of("full")
        shutil.rmtree(home / STORE)
        self.assertEqual((GOOSE.action_log(stdout, home), GOOSE.tokens(stdout, home)), ([], None))
        self.assertIsNone(GOOSE.exposure(stdout, home))
        write_store(home, {**store, "messages": [["20261114_1", "assistant", "not json"]]})
        self.assertEqual(GOOSE.action_log(stdout, home), [])
        self.assertIsNone(GOOSE.exposure(stdout, home))

    def test_a_usage_row_missing_a_count_leaves_the_counts_unknown(self):
        stdout, home, store = self.run_of("blocked")
        shutil.rmtree(home / STORE)
        write_store(home, {**store, "usage": store["usage"][:-1] + [["model-a", 5, None, 0, 1]]})
        self.assertIsNone(GOOSE.tokens(stdout, home))

    def test_a_path_is_read_from_the_working_folder_of_its_own_session(self):
        call = {"type": "toolRequest", "id": "c1", "toolCall": {"status": "success", "value": {
            "name": "write", "arguments": {"path": "out.txt", "content": "x"}}}}
        answer = {"type": "toolResponse", "id": "c1", "toolResult": {"status": "success", "value": {
            "content": [{"type": "text", "text": "Created"}], "isError": False}}}
        write_store(self.tmp, {"sessions": [["s1", "/run/project"], ["s2", "/run/project/sub"]],
                               "messages": [["s2", "assistant", json.dumps([call])], ["s2", "user", json.dumps([answer])],
                                            ["s1", "assistant", json.dumps([call])]],
                               "usage": []})
        log = GOOSE.action_log("", self.tmp)
        self.assertEqual([item["path"] for item in log], ["/run/project/sub/out.txt", "/run/project/out.txt"])
        self.assertEqual([item["kind"] for item in log], ["write", "failed"])  # the second has no answer

    def test_each_tool_s_target_is_read_from_goose_s_own_argument_name(self):
        calls = [("load_skill", {"name": "tidy/references/a.md"}), ("load_skill", {"name": "tidy"}),
                 ("read_image", {"source": "shot.png"}), ("read_image", {"source": "https://example.com/a.png"}),
                 ("shell", {"command": "cat skills/tidy/SKILL.md && cat .agents/skills/other/SKILL.md"}),
                 ("shell", {"command": "cat .agents/skills/tidy/SKILL.md.bak"})]
        answer = {"status": "success", "value": {"content": [], "structuredContent": {"exit_code": 0}}}
        messages = []
        for number, (name, arguments) in enumerate(calls):
            call = {"type": "toolRequest", "id": "same" if number < 2 else str(number),
                    "toolCall": {"status": "success", "value": {"name": name, "arguments": arguments}}}
            messages += [["s1", "assistant", json.dumps([call])],
                         ["s1", "user", json.dumps([{"type": "toolResponse", "id": call["id"], "toolResult": answer}])]]
        write_store(self.tmp, {"sessions": [["s1", "/run/project"]], "messages": messages, "usage": []})
        log = GOOSE.action_log("", self.tmp)
        self.assertEqual([(item["kind"], item.get("path") or item.get("name") or item.get("command")) for item in log], [
            ("read", "/run/project/.agents/skills/tidy/references/a.md"), ("skill", "tidy"),
            ("read", "/run/project/shot.png"), ("command", calls[4][1]["command"]), ("skill", "tidy"),
            ("skill", "other"), ("command", calls[5][1]["command"])])
        self.assertEqual([item["source"] for item in log if item["kind"] == "skill"],
                         ["observed", "inferred", "inferred"])  # a reused call id is answered by its own response


if __name__ == "__main__":
    unittest.main()
