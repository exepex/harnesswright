"""The measuring kit: its hash covers every kit file, and a round needs an approval of exactly that hash."""

import json
import unittest

from helpers import TempCase

import kit


class Kit(TempCase):
    def repo(self):
        repo = self.tmp / "repo"
        (repo / "evals" / "harness").mkdir(parents=True)
        (repo / "evals" / "harness" / "lint.py").write_text("rules = 1\n")
        (repo / "evals" / "faults").mkdir()
        (repo / "evals" / "faults" / "harness.json").write_text("{}\n")
        return repo

    def approve(self, repo, store, verdicts=("approve",) * 3):
        digest = kit.kit_hash(repo)
        folder = kit.approval_dir(store, digest)
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.json"):
            old.unlink()
        for number, verdict in enumerate(verdicts):
            (folder / f"judge-{number}.json").write_text(json.dumps({
                "judge": f"judge-{number}", "kit_sha256": digest, "files": kit.files(repo), "verdict": verdict}))

    def test_an_approved_kit_passes_and_any_change_needs_a_new_approval(self):
        repo, store = self.repo(), self.tmp / "store"
        with self.assertRaisesRegex(kit.KitError, "no judge"):
            kit.check(store, repo)
        self.approve(repo, store)
        self.assertEqual(kit.check(store, repo)["kit_sha256"], kit.kit_hash(repo))
        (repo / "evals" / "harness" / "lint.py").write_text("rules = 0\n")
        with self.assertRaisesRegex(kit.KitError, "no judge"):
            kit.check(store, repo)

    def test_every_judge_must_approve(self):
        repo, store = self.repo(), self.tmp / "store"
        self.approve(repo, store, ("approve", "approve"))
        with self.assertRaisesRegex(kit.KitError, "3 independent judges"):
            kit.check(store, repo)
        self.approve(repo, store, ("approve", "approve", "changes"))
        with self.assertRaisesRegex(kit.KitError, "all approve"):
            kit.check(store, repo)
        self.approve(repo, store)
        (repo / "evals" / "faults" / "new.json").write_text("{}\n")
        with self.assertRaisesRegex(kit.KitError, "no judge"):
            kit.check(store, repo)

    def test_the_real_kit_holds_the_harness_adapters_and_faults(self):
        names = set(kit.files())
        for path in ("evals/harness/lint.py", "evals/harness/audit.py", "evals/harness/powers.py",
                     "evals/harness/hosts.py", "evals/harness/kit.py",
                     "adapters/codex/adapter.py", "adapters/claude-code/adapter.py", "evals/faults/harness.json",
                     "evals/harness/tests/test_probes.py"):
            self.assertIn(path, names)


if __name__ == "__main__":
    unittest.main()
