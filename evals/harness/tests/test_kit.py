"""The measuring kit: its files come only from the list's parts and what git tracks, any change to them changes its
hash, and the kit check refuses a kit no judge approved, naming each file that changed."""

import json
import os
import subprocess
import sys

from helpers import TempCase

import kit
from cases import REPO

LIST = {"parts": {"lint rules": ["lint.py"], "fault catalogue": ["faults"]}}


class Kit(TempCase):
    def repo(self, parts=LIST):
        repo = self.tmp / "repo"
        (repo / kit.CODE).mkdir(parents=True, exist_ok=True)
        (repo / kit.CODE / "cases.py").write_text("PLAIN = True\n")  # code a part runs on
        (repo / "faults").mkdir(exist_ok=True)
        (repo / kit.LIST).write_text(json.dumps(parts))
        (repo / "lint.py").write_text("RULES = []\n")
        (repo / "faults" / "harness.json").write_text('{"faults": []}\n')
        self.track(repo)
        return repo

    def test_the_kit_is_the_listed_tracked_files_and_the_list(self):
        repo = self.repo()
        self.assertEqual(list(kit.files(repo)),
                         ["evals/harness/cases.py", "evals/kit.json", "faults/harness.json", "lint.py"])
        self.assertEqual(len(kit.digest(repo)), 64)

    def test_the_real_kit_is_read(self):
        found = kit.files(REPO)
        self.assertIn("evals/faults/harness.json", found)
        self.assertIn("evals/harness/powers.py", found)
        self.assertIn("evals/harness/audit.py", found)  # loaded by path, not imported, and still the kit's
        self.assertIn("evals/harness/tests/test_kit.py", found)  # the tests hold the answer keys

    def test_the_command_leaves_no_bytecode_in_the_kit(self):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}  # as an operator runs it
        done = subprocess.run([sys.executable, "evals/harness/kit.py", "hash"], cwd=REPO, env=env,
                              capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertEqual(sorted(REPO.glob("evals/harness/**/__pycache__")), [])

    def test_a_list_outside_its_rule_is_refused(self):
        for parts, reason in (({"parts": {"helpers": ["lint.py"]}}, "not parts of the kit"),
                              ({"parts": {}}, "not parts of the kit"),
                              ({"parts": {"lint rules": []}}, "not parts of the kit"),
                              ({"parts": {"lint rules": "lint.py"}}, "not a kit list"),
                              ({"parts": {"lint rules": ["missing.py"]}}, "not a file or folder git tracks"),
                              ({"parts": {"lint rules": ["../lint.py"]}}, "not a plain repository path"),
                              ({"parts": {"lint rules": ["./lint.py"]}}, "not a plain repository path")):
            with self.subTest(parts=parts), self.assertRaisesRegex(kit.KitError, reason):
                kit.files(self.repo(parts))

    def test_a_kit_folder_holding_what_git_does_not_track_is_refused(self):
        for extra in ("faults/extra.json", "evals/harness/__pycache__/cases.cpython-313.pyc"):  # read, or run
            repo = self.repo()
            (repo / extra).parent.mkdir(parents=True, exist_ok=True)
            (repo / extra).write_text("x\n")
            with self.subTest(extra=extra), self.assertRaisesRegex(kit.KitError, f"does not track: {extra}$"):
                kit.files(repo)
            os.remove(repo / extra)

    def test_a_kit_file_that_is_a_link_is_refused(self):
        repo = self.repo()
        os.remove(repo / "lint.py")
        os.symlink("faults/harness.json", repo / "lint.py")
        with self.assertRaisesRegex(kit.KitError, "not a regular file"):
            kit.files(repo)

    def test_an_approved_kit_passes_and_any_change_is_named(self):
        repo, store = self.repo(), self.tmp / "store"
        record = kit.approve(store, "judge-a", repo)
        self.assertEqual(kit.check(store, repo), record["kit"])
        self.assertEqual(json.loads((store / kit.RECORD).read_text()), record)
        (repo / "lint.py").write_text("RULES = ['looser']\n")  # an edit, before it is committed, is a change
        with self.assertRaisesRegex(kit.KitError, "differs from the one judge-a approved .*: lint.py$"):
            kit.check(store, repo)
        (repo / "lint.py").write_text("RULES = []\n")
        (repo / kit.CODE / "cases.py").write_text("PLAIN = False\n")  # code no part lists is still the kit
        with self.assertRaisesRegex(kit.KitError, "evals/harness/cases.py$"):
            kit.check(store, repo)
        (repo / kit.CODE / "cases.py").write_text("PLAIN = True\n")
        (repo / "faults" / "more.json").write_text("{}\n")
        subprocess.run(["git", "add", "faults/more.json"], cwd=repo, check=True)  # a new tracked file is a change
        with self.assertRaisesRegex(kit.KitError, "faults/more.json"):
            kit.check(store, repo)
        parts = {"parts": {"lint rules": ["lint.py"]}}  # dropping a part from the list changes the list
        (repo / kit.LIST).write_text(json.dumps(parts))
        with self.assertRaisesRegex(kit.KitError, "evals/kit.json, faults/harness.json$"):
            kit.check(store, repo)

    def test_no_approval_or_a_bad_one_is_refused(self):
        repo, store = self.repo(), self.tmp / "store"
        with self.assertRaisesRegex(kit.KitError, "no judge has approved"):
            kit.check(store, repo)
        record = kit.approve(store, "judge-a", repo)
        for broken in ("{", "7", "null", json.dumps({**record, "extra": 1}), json.dumps({**record, "kit": 7})):
            (store / kit.RECORD).write_text(broken)
            with self.subTest(broken=broken[:20]), self.assertRaisesRegex(kit.KitError, "not an approval record"):
                kit.check(store, repo)
        with self.assertRaisesRegex(kit.KitError, "names the judge"):
            kit.approve(store, " ", repo)

    def test_a_record_that_is_a_link_is_never_read_or_written_through(self):
        repo, store = self.repo(), self.tmp / "store"
        record = kit.approve(store, "judge-a", repo)
        inside = repo / "approval.json"  # a record the builder's session could edit
        inside.write_text(json.dumps(record))
        os.remove(store / kit.RECORD)
        os.symlink(inside, store / kit.RECORD)
        with self.assertRaisesRegex(kit.KitError, "not a regular file"):
            kit.check(store, repo)
        kit.approve(store, "judge-b", repo)  # the link is replaced, and the file it named is left as it was
        self.assertFalse(os.path.islink(store / kit.RECORD))
        self.assertEqual(json.loads(inside.read_text()), record)
        self.assertEqual(kit.check(store, repo), record["kit"])

    def test_the_store_is_outside_the_working_tree(self):
        repo = self.repo()
        for store in (repo, repo / "rounds"):
            with self.subTest(store=store), self.assertRaisesRegex(kit.KitError, "outside the working tree"):
                kit.approve(store, "judge-a", repo)
        os.symlink(repo, self.tmp / "via")  # a link into the tree is still the tree
        with self.assertRaisesRegex(kit.KitError, "outside the working tree"):
            kit.check(self.tmp / "via" / "rounds", repo)
