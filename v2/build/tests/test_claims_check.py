"""Tests for the claims check script, which ships in release/, so it is loaded by path. Each case breaks one thing in
a passing claims file. Run: python3 -m unittest discover -s v2/build/tests"""

import importlib.util
import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "claims_check", ROOT / "v2" / "skills" / "claims-writer" / "scripts" / "claims_check.py")
claims_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(claims_check)

STORY = """---
id: S01
plan: none
covers: [AC-1, AC-2, NFR-1, NFR-2, TD-1]   # a TD and an NFR not testable here are not requirements
tests: {AC-1: [unit], AC-2: [unit, api], NFR-1: [performance]}
targets: {NFR-1: exact, NFR-2: not testable here}
waivers: []
---

## What

Reject a negative quantity.
"""
CLAIMS = """## Request

> Reject a negative quantity.

## Requirements

### AC-1

- **Status:** met
- **Done:** `quantity` is checked, `src/pricing.py:2`.
- **Evidence:** `python3 -m unittest` printed `OK`, exit code 0.
  The output:

```text
Ran 2 tests in 0.001s
OK
```

- **Test types:**
  - unit: `test_negative`, `tests/test_pricing.py:3`

### AC-2

- **Status:** not met
- **Done:** the API returns 500, `src/pricing.py:1-3`.
- **Evidence:** `test_api` failed, `tests/test_pricing.py:5`.
- **Test types:**
  - unit: `test_zero`,
    `tests/test_pricing.py:4`
  - api: `test_api`, `tests/test_pricing.py:5`

### NFR-1

- **Status:** not verified
- **Done:** nothing to measure here.
- **Evidence:** none in this run.
- **Test types:**
  - performance: OP-1

## Open proof items

### OP-1

- **Unproven:** NFR-1, performance.
- **Proof:** the nightly load run on staging.
- **Owner:** not named

## Standards

- **rules.md:** abc

## Out of scope

- Prices: another story.

## Files changed

- `src/pricing.py` (3 lines)
- `src/old.py` (deleted)

## Not verified

- NFR-1: no staging here; see `localhost:8080`.
"""
CLAIMS_PATH = ".harness/runs/r1/claims/S01.md"


OP_BLOCK = CLAIMS[CLAIMS.index("### OP-1"):CLAIMS.index("## Standards")]
FAILS = [  # (old text, new text, the fail line it must print)
    ("### AC-1\n", "### AC-1\n\nAC-1: validation added.\n", "not a line the contract allows in Requirements"),
    ("> Reject", "Reject", "not a line the contract allows in Request"),
    ("> Reject a negative quantity.\n", "", "Request: the story is not quoted"),
    ("## Request\n", "# Claims\n\n## Request\n", "the file before Request"),
    ("## Out of scope\n\n- Prices: another story.\n\n", "", "the sections must be"),
    ("## Standards", "## Extra", "not a section of the contract, or repeats one"),
    ("## Standards\n", "## Standards\n\n## Standards\n", "not a section of the contract, or repeats one"),
    ("OK\n```", "OK\n", "a code block is not closed"),
    ("### NFR-1", "### TD-1", "NFR-1: a requirement the story covers, but it has no entry"),
    ("### NFR-1", "### TD-1", "TD-1 is not a requirement the story covers"),
    ("### AC-2", "### AC-1", "AC-1 has a second entry"),
    ("## Requirements\n\n", "## Requirements\n\n- **Status:** met\n\n", "has a line before its first entry"),
    ("- **Status:** met\n", "- **Status:** done\n", "AC-1 has Status `done`"),
    ("- **Status:** met\n", "- **Status:** met\n- **Status:** not met\n", "Status appears twice"),
    ("- **Done:** nothing to measure here.\n", "", "NFR-1 must have Status, Done"),
    ("- **Done:** nothing to measure here.", "- **Done:**", "NFR-1 has no text for Done"),
    ("- **Test types:**\n  - perf", "- **Test types:** None.\n  - perf", "**Test types** holds one line"),
    ("  - api: `test_api`, `tests/test_pricing.py:5`\n", "", "AC-2 has no api test, nor the OP-n"),
    ("performance: OP-1", "performance: OP-2", "names an OP-n that Open proof items does not define"),
    ("performance: OP-1", "performance: on staging", "give the test with a `path:line` that exists"),
    ("`tests/test_pricing.py:3`", "`tests/missing_test:3`", "`tests/missing_test:3`: no such file or line"),
    ("`tests/test_pricing.py:3`", "`tests/empty.py:1`", "AC-1, unit: give the test with a `path:line`"),
    ("- **Status:** not verified", "- **Status:** met", "NFR-1 is `met`, but OP-1 stands in"),
    ("- **Owner:** not named\n", "", "OP-1 must have Unproven, Proof, Owner"),
    ("### OP-1", "### OP-2", "must be numbered OP-1, OP-2"),
    ("- `src/old.py` (deleted)", "- `tests/test_pricing.py` (deleted)", "is marked deleted, but it exists"),
    ("### OP-1\n", "None.\n\n### OP-1\n", "Open proof items: write `None.` alone"),
    ("- Prices: another story.\n", "", "Out of scope: write `None.` alone"),
    ("(3 lines)", "(4 lines)", "`src/pricing.py` has 3 lines, not 4"),
    ("- `src/pricing.py`", "- `src/gone.py`", "`src/gone.py` does not exist"),
    ("- `src/pricing.py`", "- `/src/pricing.py`", "must be a path from the project root, listed once"),
    ("(deleted)\n", "(deleted)\n- `src/old.py` (deleted)\n", "must be a path from the project root, listed once"),
    ("- `src/pricing.py` (3 lines)\n- `src/old.py` (deleted)\n", "", "Files changed lists no file"),
    ("`tests/test_pricing.py:5`", "`tests/test_pricing.py:9`", "`tests/test_pricing.py:9`: no such file or line"),
    ("`src/pricing.py:1-3`", "`src/pricing.py:1-4`", "`src/pricing.py:1-4`: no such file or line"),
]
PASSES = [  # (old text, new text): each still passes
    ("OK\n```", "OK\n## Files changed\n```"),  # a heading in a code block is output
    ("```text\nRan 2 tests in 0.001s\nOK\n```", "  ```text\nRan 2 tests `src/x.py:9`\n  ```"),  # indented block
    ("> Reject a negative quantity.", "> Reject a negative quantity, `src/x.py:9`."),  # the request is the story's
    ("see `localhost:8080`", "see `localhost:8080`, `api.example.com:443` and `http://a.b:80`"),  # not paths
    ("`tests/test_pricing.py:3`", "`app/[id]/page.py:2`"),
    ("- **Status:** met\n", "- **Status:** `met`\n"),
    ("exit code 0.\n", "exit code 0.\n  - exit code: 0\n"),  # an indented bullet under Evidence
    ("- **Status:** not verified", "- **Status:** met"),  # with the open proof item replaced below
]


class ClaimsCheckTest(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo)
        for path, text in (("src/pricing.py", "a\nb\nc\n"), ("app/[id]/page.py", "1\n2"), ("tests/empty.py", ""),
                           ("tests/test_pricing.py", "1\n2\n3\n4\n5\n"), (".harness/runs/r1/stories/S01.md", STORY)):
            self.write(path, text)  # brackets in a name, a last line with no newline, an empty file
        self.claims = CLAIMS

    def write(self, path, text):
        (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / path).write_text(text, encoding="utf-8")

    def run_check(self, *args):
        self.write(CLAIMS_PATH, self.claims)
        out = io.StringIO()
        with redirect_stdout(out):
            code = claims_check.main(["--repo", str(self.repo), "--claims", CLAIMS_PATH, *args])
        return code, out.getvalue()

    def test_a_sound_file_passes_and_names_what_it_did_not_check(self):
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("not checked: Standards", out)
        self.assertIn("not checked: Files changed against the change: no --base given", out)

    def test_each_fault_fails_with_its_line(self):
        for old, new, expected in FAILS:
            with self.subTest(expected=expected):
                self.assertIn(old, CLAIMS)
                self.claims = CLAIMS.replace(old, new)
                code, out = self.run_check()
                self.assertEqual(code, 1, out)
                self.assertIn(expected, out)

    def test_what_the_contract_allows_passes(self):
        for old, new in PASSES:
            with self.subTest(new=new):
                self.assertIn(old, CLAIMS)
                self.claims = CLAIMS.replace(old, new)
                if new == "- **Status:** met":
                    self.claims = self.claims.replace(OP_BLOCK, "None.\n\n").replace("OP-1", "`src/pricing.py:1`")
                code, out = self.run_check()
                self.assertEqual(code, 0, out)

    def test_the_story_frontmatter(self):
        self.write(".harness/runs/r1/stories/S01.md", STORY.replace("NFR-1, NFR-2, TD-1]", "NFR-2, TD-1]"))
        self.claims = CLAIMS.replace(CLAIMS[CLAIMS.index("### AC-1"):CLAIMS.index("## Open")], "None.\n\n")
        self.assertEqual(self.run_check()[0], 1)  # it covers AC-1 and AC-2
        self.write(".harness/runs/r1/stories/S01.md", STORY.replace("AC-1, AC-2, NFR-1, NFR-2, TD-1]", "NFR-2, TD-1]"))
        self.assertEqual(self.run_check()[0], 0)  # a story that covers no requirement
        self.write(".harness/runs/r1/stories/S01.md", "## What\n\nNo frontmatter.\n")
        self.assertIn("not checked: requirements against the story", self.run_check()[1])
        self.write(".harness/runs/r1/stories/S01.md", STORY.replace(
            "tests: {AC-1: [unit], AC-2: [unit, api], NFR-1: [performance]}", "tests:\n  AC-1: [unit]"))
        self.assertIn("flow form", self.run_check()[1])
        self.write(".harness/runs/r1/stories/S01.md", STORY.replace("[AC-1, AC-2,", "['AC-1', 'AC-2',"))
        self.assertIn("flow form", self.run_check()[1])  # a quoted ID is not the contract's form
        self.assertEqual(self.run_check("--story", "missing.md")[0], 2)

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_files_changed_equals_the_change(self):
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        self.write("src/old.py", "x\n")
        self.write("src/moved.py", "m\n")
        subprocess.run([*git, "init", "-q"], cwd=self.repo, check=True)
        subprocess.run([*git, "add", "."], cwd=self.repo, check=True)
        subprocess.run([*git, "commit", "-qm", "base"], cwd=self.repo, check=True)
        (self.repo / "src/old.py").unlink()
        subprocess.run([*git, "mv", "src/moved.py", "src/renamed.py"], cwd=self.repo, check=True)
        self.write("src/pricing.py", "a\nb\nC\n")
        self.write("src/new.py", "n\n")
        code, out = self.run_check("--base", "HEAD")
        self.assertIn("`src/new.py` changed since HEAD, but Files changed does not list it", out)
        self.assertNotIn("`.harness", out)  # the run folder is not part of the change
        self.claims = CLAIMS.replace("(deleted)\n", "(deleted)\n- `src/new.py` (1 line)\n- `src/moved.py` (deleted)\n"
                                     "- `src/renamed.py` (1 line)\n")
        self.assertEqual(self.run_check("--base", "HEAD")[0], 0)  # a rename is a deletion and a new file
        self.claims = self.claims.replace("(1 line)\n", "(1 line)\n- `tests/test_pricing.py` (5 lines)\n", 1)
        self.assertIn("did not change since HEAD", self.run_check("--base", "HEAD")[1])


if __name__ == "__main__":
    unittest.main()
