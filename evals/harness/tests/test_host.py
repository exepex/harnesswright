"""Hosts: the harness knows a host only through one contract, and accepts only what its allow lists describe."""

import importlib.util
import json
import shutil
import types
import unittest
from pathlib import Path

from helpers import SKILL_MD, TempCase

import contain
import host
import manifest

JAIL = contain.available()
FAKE = Path(__file__).resolve().parent / "fakehost"


def fake_adapter():
    spec = importlib.util.spec_from_file_location("fakehost_adapter", FAKE / "adapter.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def changed(adapter, **names):
    """A copy of `adapter` with some names replaced, as a planted fault."""
    return types.SimpleNamespace(**{**{n: getattr(adapter, n) for n in dir(adapter) if not n.startswith("__")},
                                    **names})


class Contract(unittest.TestCase):
    def test_an_adapter_must_define_every_name_of_the_contract(self):
        adapter = fake_adapter()
        host.check_adapter(adapter)
        broken = changed(adapter, action_log=None, TOOLS={**adapter.TOOLS, "web_search": "web"})
        with self.assertRaisesRegex(host.HostError, "action_log is missing.*tool web_search has kind 'web'"):
            host.check_adapter(broken)

    def test_the_action_log_takes_only_the_entries_it_lists(self):
        good = [host.entry("read", path="a"), host.entry("read", "inferred", path="b"),
                host.entry("write", path="a", sha256=host.sha256("x")), host.entry("write", path="a", sha256=None),
                host.entry("command", command="ls", exit_code=0, output="x" * 9000),
                host.entry("blocked", action="shell: rm", reason="denied"), host.entry("skill", name="s"),
                host.entry("agent", task="judge"), host.entry("message", text="done")]
        host.check_log(good)
        self.assertEqual(len(good[4]["output"]), host.OUTPUT_LIMIT)
        for bad in ({"kind": "web", "source": "observed"}, {**good[0], "extra": 1}, {**good[0], "source": "guessed"},
                    {**good[2], "sha256": "abc"}, {**good[4], "exit_code": True}, {**good[4], "output": "x" * 4001},
                    {"kind": "read", "source": "observed"}, "read a", {"kind": ["read"], "source": "observed"}):
            with self.subTest(bad=bad), self.assertRaises(host.HostError):
                host.check_log([bad])
        with self.assertRaisesRegex(host.HostError, "not a list"):
            host.check_log(good[0])

    def test_a_host_may_expose_only_the_declared_skills_and_the_adapters_tools(self):
        adapter = fake_adapter()
        host.check_exposure(adapter, {"skills": ["haiku-writer"], "tools": ["shell"]}, ["haiku-writer"])
        for exposure, reason in (({"skills": ["fake-helper"], "tools": []}, "skill fake-helper is exposed"),
                                 ({"skills": [], "tools": ["clock"]}, "tool clock is exposed"),
                                 ({"skills": []}, "exposure is not")):
            with self.subTest(exposure=exposure), self.assertRaisesRegex(host.HostError, reason):
                host.check_exposure(adapter, exposure, ["haiku-writer"])


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class FakeHost(TempCase):
    """The fake host runs in a real jail, so the contract is shown end to end without a model."""

    def run_of(self, mode, adapter, actions, tokens=()):
        tool = self.tmp / "tool"
        if not tool.exists():
            shutil.copytree(FAKE, tool, ignore=shutil.ignore_patterns("adapter.py", "__pycache__"))
        world = self.tmp / f"world-{mode}"
        if not world.exists():
            (world / ".fake" / "skills" / "haiku-writer").mkdir(parents=True)
            (world / ".fake" / "skills" / "haiku-writer" / "SKILL.md").write_text(SKILL_MD)
            (world / "README.md").write_text("A notes app.\n")
        root = self.tmp / f"run-{len(list(self.tmp.glob('run-*')))}"
        contained = contain.Containment(adapter, mode, world, manifest.manifest(world), root=root,
                                        operator_env={"PATH": f"{tool}:/usr/bin:/bin"},
                                        operator_home=self.tmp / "operator", host_paths=[tool], tokens=tokens)
        return host.run(contained, json.dumps(actions), skills=["haiku-writer"], timeout=120), world

    def test_a_sound_run_gives_one_host_neutral_log(self):
        notes = str((self.tmp / "world-task").resolve() / "notes.txt")  # an absolute path is logged in world terms
        actions = [{"do": "read", "path": "README.md"}, {"do": "write", "path": notes, "text": "hi\n"},
                   {"do": "command", "command": "cat README.md"}, {"do": "skill", "name": "haiku-writer"},
                   {"do": "agent", "task": "judge the change"}, {"do": "read", "path": "missing.txt"},
                   {"do": "write", "path": "no-folder/x.txt", "text": "x"},  # failed, but the run may write there
                   {"do": "command", "command": "rm -r .", "block": "no"}, {"do": "say", "text": "Done."}]
        result, world = self.run_of("task", fake_adapter(), actions)
        self.assertIsNone(result.failure, result.stderr)
        self.assertEqual(result.log, [
            host.entry("read", path="README.md"), host.entry("write", path="notes.txt", sha256=host.sha256("hi\n")),
            host.entry("command", command="cat README.md", exit_code=0, output="A notes app.\n"),
            host.entry("read", "inferred", path="README.md"), host.entry("skill", name="haiku-writer"),
            host.entry("agent", task="judge the change"), host.entry("blocked", action="shell: rm -r .", reason="no"),
            host.entry("message", text="Done.")])
        self.assertEqual(result.exposure, {"skills": ["haiku-writer"], "tools": list(fake_adapter().TOOLS)})
        self.assertEqual((world / "notes.txt").read_text(), "hi\n")
        self.assertEqual(result.requests, [])

    def test_the_jail_not_the_host_decides_what_a_run_may_write(self):
        result, world = self.run_of("trigger", fake_adapter(), [{"do": "write", "path": "notes.txt", "text": "x"}])
        # The host's sandbox is off; the jail refused the write, and the log says so.
        self.assertEqual([(e["kind"], e["action"]) for e in result.log], [("blocked", "write_file: notes.txt")])
        self.assertIn("does not let a trigger run write it: [Errno 30]", result.log[0]["reason"])
        self.assertFalse((world / "notes.txt").exists())
        sandboxed = changed(fake_adapter(), jail_command=lambda mode, world, model: [
            "fakehost", "--world", str(world), "--no-bundled", "--tools", "write_file"])
        result, _ = self.run_of("task", sandboxed, [{"do": "write", "path": "notes.txt", "text": "x"}])
        self.assertEqual([e["kind"] for e in result.log], ["blocked"])  # a host block is logged, the same everywhere

    def test_a_host_that_exposes_more_than_the_case_stops_the_round(self):
        adapter = fake_adapter()
        for command, reason in ((["--sandbox", "off", "--tools", ",".join(adapter.TOOLS)], "skill fake-helper"),
                                (["--sandbox", "off", "--no-bundled"], "tool clock")):
            faulty = changed(adapter, jail_command=lambda mode, world, model, c=command: [
                "fakehost", "--world", str(world)] + c)
            with self.subTest(reason=reason), self.assertRaisesRegex(host.HostError, reason):
                self.run_of("task", faulty, [])

    def test_run_checks_the_adapter_the_jail_the_log_and_records_the_gate(self):
        adapter = fake_adapter()
        with self.assertRaisesRegex(host.HostError, "tool web_search has kind 'web'"):
            self.run_of("task", changed(adapter, TOOLS={**adapter.TOOLS, "web_search": "web"}), [])
        token = contain.new_token()
        (self.tmp / "world-task" / "notes.txt").write_text(f"left here: {token}\n")  # a leak the audit must find
        with self.assertRaisesRegex(contain.ContainmentError, "a canary token is in .*notes.txt"):
            self.run_of("task", adapter, [], tokens=[token])
        (self.tmp / "world-task" / "notes.txt").unlink()
        bad = changed(adapter, action_log=lambda stdout, home: [{"kind": "read", "source": "observed", "path": 1}])
        with self.assertRaisesRegex(host.HostError, "action log: entry 0 \\(read\\): path"):
            self.run_of("task", bad, [])
        hiding = changed(adapter, exposure=lambda stdout, home: {"skills": ["haiku-writer"], "tools": []},
                         jail_command=lambda mode, world, model: ["fakehost", "--world", str(world)])
        with self.assertRaisesRegex(host.HostError, "skill fake-helper was loaded but the case does not declare"):
            self.run_of("task", hiding, [{"do": "skill", "name": "fake-helper"}])
        with self.assertRaisesRegex(host.HostError, "did not report the skills and tools it exposed"):
            self.run_of("task", changed(adapter, exposure=lambda stdout, home: None), [])
        call = ("import socket; s = socket.create_connection(('127.0.0.1', 3128)); "
                "s.sendall(b'CONNECT off.example:443 HTTP/1.1\\r\\n\\r\\n'); s.recv(99)")
        result, _ = self.run_of("task", adapter, [{"do": "command", "command": f'python3 -c "{call}"'}])
        self.assertEqual(result.requests, [{"request": "CONNECT off.example:443 HTTP/1.1", "status": 403}])

    def test_a_host_that_crashes_is_a_failure(self):
        crashed = changed(fake_adapter(), jail_command=lambda mode, world, model: ["fakehost", "--no-such-flag"])
        result, _ = self.run_of("task", crashed, [])
        self.assertEqual(result.failure, "exit code 2")


if __name__ == "__main__":
    unittest.main()
