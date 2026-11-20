"""Shared pieces of the harness tests: a temporary folder per test, and small skills and cases."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
# A commit holding the last verified version of both claims-writer and skill-designer (evals/results), which a plan
# of their task cases names as previous once each has changed since (versions.verified).
VERIFIED_AT = "53c6ea70a9eb8aaadb714b6ea8b32303b3efef44"
sys.path.insert(0, str(HARNESS))
SKILL_MD = ("---\nname: haiku-writer\ndescription: Writes a haiku about the project's purpose. Use when asked for a "
            "haiku about this project.\n---\n\n# Haiku writer\n\nCount the syllables of every line twice before you "
            "answer, five then seven then five, and never rhyme the last word.\n")

JUDGED = {"question": "Does it hold?", "pass": "It holds.", "fail": "It does not.",
          "examples": {"pass": ["A run where it holds."], "fail": ["A run where it does not."]}}


def expect(text, source="format", check=None):
    """An expectation of `text` from `source`, judged, and decided first by `check` ({name, args}) when given."""
    return {"text": text, "source": source, "judged": JUDGED, **({"check": check} if check else {})}


class TempCase(unittest.TestCase):
    """A test with its own temporary folder, `self.tmp`, removed afterwards."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hw-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def skill(self, name="haiku-writer", text=SKILL_MD):
        folder = self.tmp / "skills" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text(text.replace("haiku-writer", name))
        self.track(folder.parent)
        return folder

    def release_skill(self, name="claims-writer"):
        """A team skill as the release ships it: its folder beside run-time files and a manifest hashing both."""
        import hashlib
        folder = self.skill(name)
        root = folder.parent
        for rel, text in {"roles.md": "# Roles\n", "rules/core/work.md": "# Work\n"}.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text)

        def hashes(base, rels):
            return {rel: hashlib.sha256((base / rel).read_bytes()).hexdigest() for rel in rels}

        skills = {n: {"files": hashes(root / n, sorted(p.relative_to(root / n).as_posix()
                                                         for p in (root / n).rglob("*") if p.is_file()))}
                  for n in sorted(p.name for p in root.iterdir() if (p / "SKILL.md").is_file())}
        (root / "manifest.json").write_text(json.dumps({
            "rulebook-version": "0.8.0", "skills": skills, "run-time": ["manifest.json", "roles.md", "rules/"],
            "run-time-files": hashes(root, ["roles.md", "rules/core/work.md"])}, indent=2) + "\n")
        self.track(root)
        return folder

    def track(self, folder):
        """Make git track every file under `folder`, as a skill's files are tracked in the repository."""
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        for args in (["init", "-q"], ["add", "-A"]):
            subprocess.run(["git", *args], cwd=folder, env=env, check=True, capture_output=True)

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
