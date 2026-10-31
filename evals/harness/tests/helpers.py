"""Shared pieces of the harness tests: a temporary folder per test, a fake host installed outside the
repository, and small skills and cases."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
import hosts  # noqa: E402
import contain  # noqa: E402

FAKE = Path(__file__).resolve().parent / "fakehost"
SKILL_MD = ("---\nname: haiku-writer\ndescription: Writes a haiku about the project's purpose. Use when asked for a "
            "haiku about this project.\n---\n\n# Haiku writer\n\nCount the syllables of every line twice before you "
            "answer, five then seven then five, and never rhyme the last word.\n")
FAKE_ENV = {"PATH": "/usr/bin:/bin", "FAKE_HOST_KEY": "fake-key-0123456789abcdef"}


class TempCase(unittest.TestCase):
    """A test with its own temporary folder, `self.tmp`, removed afterwards."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hw-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def skill(self, name="haiku-writer", text=SKILL_MD):
        folder = self.tmp / "skills" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text(text.replace("haiku-writer", name))
        return folder

    def case(self, files, data=None, name=None, skill="haiku-writer"):
        """A case folder with `files` ({path: text}) in its world and `data` as case.json."""
        root = self.tmp / "cases"
        folder = root / (name or f"c{len(list(root.iterdir())) + 1 if root.is_dir() else 1}")
        world = folder / "world"
        world.mkdir(parents=True)
        for path, text in files.items():
            (world / path).parent.mkdir(parents=True, exist_ok=True)
            (world / path).write_text(text)
        body = {"prompt": "Write a short poem about this notes app.", "kind": "task"}
        body.update(data or {})
        (folder / "case.json").write_text(json.dumps(body))
        import cases
        return cases.Case(folder, skill)

    def fake_adapter(self):
        """The fake host's adapter, with the program installed in a folder of its own outside the repository."""
        installs = self.tmp / "fake-install"
        install = installs / str(len(list(installs.iterdir())) if installs.is_dir() else 0) / "bin"
        install.mkdir(parents=True)
        program = install / "fake-host"
        shutil.copy2(FAKE / "fake_host.py", program)
        program.chmod(0o755)
        adapter = hosts.load("fake", FAKE / "adapter.py")
        adapter.CLI = str(program)
        return adapter

    def operator_env(self, **extra):
        env = dict(FAKE_ENV)
        for key in ("HTTPS_PROXY", "SSL_CERT_FILE", "LANG"):
            if key in os.environ:
                env[key] = os.environ[key]
        env.update(extra)
        return env


def needs_jail(test):
    """Skip a test where this machine cannot contain runs."""
    reason = contain.available()
    return unittest.skipIf(reason is not None, f"no containment here: {reason}")(test)
