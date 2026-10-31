"""Shared pieces of the harness tests: a temporary folder per test, and small cases."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))


class TempCase(unittest.TestCase):
    """A test with its own temporary folder, `self.tmp`, removed afterwards."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hw-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

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
