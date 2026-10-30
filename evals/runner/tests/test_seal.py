"""Fault tests for sealed host runs: planted copies of the skill, planted memory and session variables,
and a planted home folder must all be out of a run's reach, while the host can still sign in."""

import json
import os
import shutil
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402
import seal  # noqa: E402

SKILL_MD = "---\nname: demo\ndescription: Writes demo haiku for the seal test.\n---\n# Demo\n"

# Runs inside the sealed host: reports what it can see and do, as one JSON line.
PROBE = textwrap.dedent("""
    import json, os, sys
    targets = json.loads(sys.argv[1])
    def can_write(folder):
        try:
            with open(os.path.join(folder, "probe-write"), "w") as handle:
                handle.write("x")
            return True
        except OSError:
            return False
    print(json.dumps({
        "seen": {name: os.path.exists(path) for name, path in targets.items()},
        "through_proc": sorted(name for name, path in targets.items() for pid in os.listdir("/proc")
                               if pid.isdigit() and os.path.exists(f"/proc/{pid}/root{path}")),
        "env": sorted(os.environ),
        "home": sorted(os.listdir(os.environ["HOME"])),
        "tmp": sorted(os.listdir("/tmp")),
        "writes_workspace": can_write("."),
        "writes_etc": can_write("/etc"),
    }))
""")


def probe_adapter():
    return types.SimpleNamespace(
        NAME="probe", CLI=sys.executable, ENV_KEYS=("PROBE_API_KEY",),
        CREDENTIAL_FILES=(".probe/auth.json",),
        environment=lambda env: env, skill_dir=lambda workspace, name: Path(workspace) / ".probe" / name,
        build_command=lambda mode, workspace, model, scratch=None: [sys.executable, "-I", "probe.py"],
        parse_events=lambda out: [json.loads(line) for line in out.splitlines() if line.startswith("{")],
        refusals=lambda events: [], resolved_model=lambda events: None,
        failure=lambda events, code, timed_out, mode: None if code == 0 else f"exit code {code}")


class EnvironmentSealTest(unittest.TestCase):
    def test_only_allowed_variables_pass(self):
        source = {"PATH": "/usr/bin", "PROBE_API_KEY": "k", "CLAUDE_CODE_SESSION_ID": "operator",
                  "CLAUDE_MEMORY_STORES": "team", "TMPDIR": "/operator/tmp", "HOME": "/operator"}
        with tempfile.TemporaryDirectory() as home:
            env = seal.environment(probe_adapter(), Path(home), source=source)
        self.assertEqual(env["PROBE_API_KEY"], "k")
        self.assertEqual(env["HOME"], home)
        self.assertEqual(env["TMPDIR"], str(Path(home) / "tmp"))
        for planted in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_MEMORY_STORES"):
            self.assertNotIn(planted, env)

    def test_shipped_adapters_pass_their_sign_in_only(self):
        source = {"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "a", "OPENAI_API_KEY": "o",
                  "CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "operator"}
        with tempfile.TemporaryDirectory() as home:
            claude = seal.environment(core.load_adapter("claude-code"), Path(home), source=source)
            codex = seal.environment(core.load_adapter("codex"), Path(home), source=source)
        self.assertEqual((claude.get("ANTHROPIC_API_KEY"), claude.get("OPENAI_API_KEY")), ("a", None))
        self.assertEqual((codex.get("OPENAI_API_KEY"), codex.get("ANTHROPIC_API_KEY")), ("o", None))
        for env in (claude, codex):
            self.assertFalse([key for key in env if key.startswith("CLAUDE")])

    def test_private_home_copies_credentials_only(self):
        with tempfile.TemporaryDirectory() as real_home:
            Path(real_home, ".probe").mkdir()
            Path(real_home, ".probe", "auth.json").write_text("{}")
            Path(real_home, ".memory").mkdir()
            Path(real_home, ".memory", "project.md").write_text("the skill is at skills/demo")
            with mock.patch.dict(os.environ, {"HOME": real_home}):
                home = seal.make_home(probe_adapter())
        try:
            files = sorted(str(p.relative_to(home)) for p in home.rglob("*") if p.is_file())
            self.assertEqual(files, [".probe/auth.json"])
        finally:
            shutil.rmtree(home)


class HostInstallTest(unittest.TestCase):
    def test_install_prefix_and_package_folder_are_mounted(self):
        with tempfile.TemporaryDirectory() as root:
            prefix = Path(root) / "node-v1"
            package = prefix / "lib" / "tool"
            package.mkdir(parents=True)
            (package / "cli.py").write_text("")
            (prefix / "bin").mkdir()
            (prefix / "bin" / "tool").symlink_to(package / "cli.py")
            with mock.patch.object(seal.shutil, "which", return_value=str(prefix / "bin" / "tool")):
                self.assertEqual(seal.host_install("tool"), [prefix, package.resolve()])

    def test_program_in_home_bin_mounts_the_file_only(self):
        with tempfile.TemporaryDirectory() as home:
            program = Path(home) / "bin" / "tool"
            program.parent.mkdir()
            program.write_text("")
            with mock.patch.dict(os.environ, {"HOME": home}), \
                    mock.patch.object(seal.shutil, "which", return_value=str(program)):
                self.assertEqual(seal.host_install("tool"), [program])

    def test_system_programs_need_no_mount(self):
        with mock.patch.object(seal.shutil, "which", return_value="/usr/bin/python3"):
            self.assertEqual(seal.host_install("python3"), [])


@unittest.skipUnless(seal.jail_available() and sys.platform.startswith("linux"), "needs bwrap on Linux")
class JailTest(unittest.TestCase):
    """A sealed run of a probe host with the skill planted where earlier baselines found it."""

    def setUp(self):
        self.planted = Path(tempfile.mkdtemp(prefix="hw-eval-planted-"))
        (self.planted / "skills" / "demo").mkdir(parents=True)
        (self.planted / "skills" / "demo" / "SKILL.md").write_text(SKILL_MD)
        self.addCleanup(shutil.rmtree, self.planted)

    def run_probe(self, **env):
        adapter = probe_adapter()
        workspace = core.make_workspace(adapter, None, "demo")
        self.addCleanup(shutil.rmtree, workspace, True)
        (workspace / "probe.py").write_text(PROBE)
        targets = {"other run's skill": str(self.planted / "skills" / "demo"),
                   "repository checkout": str(core.REPO_ROOT / "skills"),
                   "repository history": str(core.REPO_ROOT / ".git"),
                   "operator settings": os.path.expanduser("~/.claude")}
        planted = {"CLAUDE_CODE_SESSION_ID": "operator", "CLAUDE_MEMORY_STORES": "team", **env}
        with mock.patch.dict(os.environ, planted):
            with mock.patch.object(adapter, "build_command", lambda *a, **k: [
                    sys.executable, "-I", "probe.py", json.dumps(targets)]):
                run = core.run_host(adapter, workspace, "", "task", None, 60)
        self.assertIsNone(run["failure"], run["stderr"])
        return run["events"][-1]

    def test_planted_skill_copies_are_out_of_reach(self):
        report = self.run_probe()
        self.assertEqual(report["seen"], {name: False for name in report["seen"]})
        self.assertEqual(report["through_proc"], [])

    def test_operator_session_and_memory_do_not_pass(self):
        report = self.run_probe(PROBE_API_KEY="k")
        self.assertIn("PROBE_API_KEY", report["env"])
        self.assertFalse([key for key in report["env"] if key.startswith("CLAUDE")])
        self.assertEqual(report["home"], ["tmp"])
        self.assertNotIn(self.planted.name, report["tmp"])

    def test_host_installed_outside_system_folders_runs(self):
        prefix = Path(tempfile.mkdtemp(prefix="hw-host-"))
        self.addCleanup(shutil.rmtree, prefix)
        (prefix / "bin").mkdir()
        program = prefix / "bin" / "probe-host"
        program.write_text(f"#!{sys.executable} -I\nimport json; print(json.dumps({{'ran': True}}))\n")
        program.chmod(0o755)
        adapter = probe_adapter()
        adapter.build_command = lambda *a, **k: ["probe-host"]
        workspace = core.make_workspace(adapter, None, "demo")
        self.addCleanup(shutil.rmtree, workspace, True)
        with mock.patch.dict(os.environ, {"PATH": f"{prefix / 'bin'}:{os.environ['PATH']}"}):
            run = core.run_host(adapter, workspace, "", "task", None, 60)
        self.assertIsNone(run["failure"], run["stderr"])
        self.assertEqual(run["events"], [{"ran": True}])

    def test_workspace_is_writable_and_system_folders_are_not(self):
        report = self.run_probe()
        self.assertTrue(report["writes_workspace"])
        self.assertFalse(report["writes_etc"])


if __name__ == "__main__":
    unittest.main()
