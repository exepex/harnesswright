"""The goose adapter's first part gives the harness contract: its command, powers, plants, memory places, failures
and what it reads of the exposure from the requests goose logs."""

import json
import unittest
from pathlib import Path

from helpers import TempCase
from test_adapters import adapter
from test_goose_events import write_store

import host
import powers

GOOSE = adapter("goose")


OPENING = GOOSE.SKILLS_OPENING


def request(tools=("shell", "load_skill"), system=f"You are goose.\n\n# Skills\n\n{OPENING}\n- tidy: ok\n\n# Hints"):
    """A logged request as goose writes it: its first line holds the model's settings and the request."""
    return {"model_config": {"model_name": "model-a"},
            "input": {"messages": [{"role": "system", "content": system}, {"role": "user", "content": "hi"}],
                      "tools": [{"type": "function", "function": {"name": name}} for name in tools]}}


class Command(unittest.TestCase):
    def test_the_adapter_gives_the_whole_contract_on_one_route(self):
        host.check_adapter(GOOSE)
        self.assertEqual((GOOSE.ENV_KEYS, GOOSE.MODEL_HOSTS), (("OPENROUTER_API_KEY",), ("openrouter.ai",)))
        self.assertTrue(set(GOOSE.TOOLS.values()) <= set(powers.TOOLS))

    def test_the_command_reads_stdin_keeps_no_session_and_turns_on_one_extension(self):
        self.assertEqual(GOOSE.jail_command("trigger", "/w", None), [
            "goose", "run", "-i", "-", "--output-format", "stream-json", "--no-session", "--no-profile",
            "--with-builtin", "developer,summon", "--provider", "openrouter"])
        self.assertEqual(GOOSE.jail_command("task", "/w", "m")[-2:], ["--model", "m"])

    def test_every_run_has_auto_mode_and_the_bundled_skills_off(self):
        self.assertEqual(GOOSE.RUN_ENV["GOOSE_MODE"], "auto")
        self.assertEqual(GOOSE.RUN_ENV["GOOSE_BUILTIN_SKILLS"], "false")

    def test_each_plant_changes_the_command(self):
        command = GOOSE.jail_command("task", "/w", "m")
        self.assertEqual(GOOSE.PLANTS["bundled skills"](command), ["env", "GOOSE_BUILTIN_SKILLS=true"] + command)
        planted = GOOSE.PLANTS["no commands"](command)
        self.assertNotIn("--with-builtin", planted)
        self.assertEqual(len(planted), len(command) - 2)

    def test_memory_places_lie_outside_the_world(self):
        home, world = Path("/h"), Path("/p/w")
        places = [str(p) for p in GOOSE.memory_files(home, world)]
        self.assertEqual(places[:2], ["/h/.config/goose/.goosehints", "/h/.config/goose/AGENTS.md"])
        self.assertEqual(places[2:11], [f"/h/.config/goose/prompts/{name}" for name in GOOSE.PROMPTS])
        self.assertEqual(places[11:], [
            "/h/.agents/AGENTS.md", "/h/.goose/agents/hw-probe.md", "/h/.agents/agents/hw-probe.md",
            "/h/.config/goose/agents/hw-probe.md", "/h/.claude/agents/hw-probe.md", "/h/.goose/recipes/hw-probe.yaml",
            "/h/.config/goose/recipes/hw-probe.yaml", "/h/.agents/recipes/hw-probe.yaml", "/p/.goosehints",
            "/p/AGENTS.md"])
        self.assertEqual(GOOSE.skill_dir("/w", "tidy"), Path("/w/.agents/skills/tidy"))


class Failure(unittest.TestCase):
    def lines(self, *items):
        return "\n".join(json.dumps(item) for item in items)

    def test_a_run_succeeds_only_with_a_complete_event_and_no_error(self):
        done = self.lines({"type": "message", "message": {}}, {"type": "complete", "total_tokens": 3})
        self.assertIsNone(GOOSE.run_failure(done, 0, False))
        self.assertEqual(GOOSE.run_failure(self.lines({"type": "message"}), 0, False), "no complete event")
        self.assertEqual(GOOSE.run_failure(self.lines({"type": "error", "error": "no key"}), 1, False),
                         "host reported error: no key")
        self.assertEqual(GOOSE.run_failure("", None, True), "timed out")
        self.assertEqual(GOOSE.run_failure("not json", 2, False), "exit code 2")


class Exposure(TempCase):
    """Each logged request here was answered, and the session store holds one usage row for each."""

    def setUp(self):
        super().setUp()
        self.answered = 0

    def log(self, number, *records):
        folder = self.tmp / ".local" / "state" / "goose" / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(record) for record in records] + [json.dumps({"data": None, "usage": {"input_tokens": 1}})]
        path = folder / f"llm_request.{number}.jsonl"
        self.answered += not path.exists()
        path.write_text("\n".join(lines) + "\n")
        store = self.tmp / ".local" / "share" / "goose" / "sessions" / "sessions.db"
        store.unlink(missing_ok=True)
        write_store(self.tmp, {"sessions": [], "messages": [], "usage": [["model-a", 1, 0, 0, 1]] * self.answered})

    def test_the_exposure_is_every_tool_and_skill_of_every_logged_request(self):
        self.log(0, request())
        system = f"# Skills\n\n{OPENING}\n- tidy: ok\n- other: two words\n\n# End"
        self.log(1, request(tools=("shell", "write"), system=system))
        self.assertEqual(GOOSE.exposure("", self.tmp),
                         {"skills": ["other", "tidy"], "tools": ["load_skill", "shell", "write"]})

    def test_rows_outside_a_skills_heading_are_not_skills(self):
        self.log(0, request(system=f"# Rules\n- tidy: not a skill\n# Skills\n\n{OPENING}\n- real: yes"))
        self.assertEqual(GOOSE.exposure("", self.tmp)["skills"], ["real"])

    def test_a_row_that_does_not_parse_is_kept_whole_and_stops_the_round(self):
        self.log(0, request(system=f"# Skills\n\n{OPENING}\n- not a skill row"))
        exposure = GOOSE.exposure("", self.tmp)
        self.assertEqual(exposure["skills"], ["- not a skill row"])
        with self.assertRaises(host.HostError):
            host.check_exposure(GOOSE, exposure, [])

    def test_a_description_on_more_lines_is_kept_whole_and_hides_no_later_row(self):
        self.log(0, request(system=f"# Skills\n\n{OPENING}\n- tidy: one\n# not a heading\n- other: two\n\n"
                                   "- later: after a blank line\n\n# Extensions\n- hidden: not a skill"))
        self.assertEqual(GOOSE.exposure("", self.tmp)["skills"], ["# not a heading", "later", "other", "tidy"])

    def test_a_list_without_goose_s_opening_is_not_a_skill_part(self):
        self.log(0, request(system="# Skills\n- tidy: not goose's list"))
        self.assertEqual(GOOSE.exposure("", self.tmp)["skills"], [])

    def test_no_log_or_one_in_another_form_is_no_report(self):
        self.assertIsNone(GOOSE.exposure("", self.tmp))
        self.log(0, {"input": {"tools": []}})
        self.assertIsNone(GOOSE.exposure("", self.tmp))
        self.log(0, {"input": {"messages": [], "tools": [{"function": "shell"}]}})
        self.assertIsNone(GOOSE.exposure("", self.tmp))

    def test_a_tool_off_the_list_stops_the_round(self):
        self.log(0, request(tools=("shell", "fetch")))
        with self.assertRaises(host.HostError):
            host.check_exposure(GOOSE, GOOSE.exposure("", self.tmp), ["tidy"])


if __name__ == "__main__":
    unittest.main()
