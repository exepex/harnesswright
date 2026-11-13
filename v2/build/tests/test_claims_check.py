"""Tests for the claims writer's check script. Run: python3 -m unittest discover -s v2/build/tests

The script ships in release/claims-writer/scripts/, so it is loaded by path. Each test writes a small project with a
story and a claims file that passes, then breaks one thing.
"""

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
covers: [AC-1, AC-2, NFR-1]   # what this story delivers
tests: {AC-1: [unit], AC-2: [unit, api], NFR-1: [performance]}
targets: {NFR-1: not testable here}
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


class ClaimsCheckTest(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo)
        self.write("src/pricing.py", "a\nb\nc\n")
        self.write("tests/test_pricing.py", "1\n2\n3\n4\n5\n")
        self.write(".harness/runs/r1/stories/S01.md", STORY)
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

    def fails_with(self, old, new, expected, *args):
        self.assertIn(old, self.claims)
        self.claims = self.claims.replace(old, new)
        code, out = self.run_check(*args)
        self.assertEqual(code, 1, out)
        self.assertIn(expected, out)

    def test_a_sound_file_passes_and_names_what_it_did_not_check(self):
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("not checked: Standards", out)
        self.assertIn("not checked: Files changed against the change: no --base given", out)

    def test_every_line_must_be_a_shape_the_contract_allows(self):
        self.fails_with("### AC-1\n", "### AC-1\n\nAC-1: validation added, tests should pass.\n",
                        "not a line the contract allows in Requirements")
        self.fails_with("> Reject", "Reject", "not a line the contract allows in Request")
        self.fails_with("## Request\n", "# Claims\n\n## Request\n", "the file before Request")

    def test_sections_in_order(self):
        self.fails_with("## Out of scope\n\n- Prices: another story.\n\n", "", "the sections must be")
        self.claims = CLAIMS.replace("## Standards", "## Extra")
        self.assertIn("not a section of the contract", self.run_check()[1])

    def test_a_heading_inside_a_code_block_is_output(self):
        self.claims = CLAIMS.replace("OK\n```", "OK\n## Files changed\n```")
        self.assertEqual(self.run_check()[0], 0)
        self.fails_with("OK\n## Files changed\n```", "OK\n", "a code block is not closed")

    def test_one_entry_per_requirement_the_story_covers(self):
        self.fails_with("### NFR-1", "### NFR-2", "NFR-1: the story covers it, but it has no entry")
        self.assertIn("NFR-2 is not a requirement the story covers", self.run_check()[1])
        self.claims = CLAIMS
        self.fails_with("### AC-2", "### AC-1", "AC-1 has a second entry")

    def test_fields_in_order_and_status_words(self):
        self.fails_with("- **Status:** met\n", "- **Status:** done\n", "AC-1 has Status `done`")
        self.claims = CLAIMS
        self.fails_with("- **Done:** nothing to measure here.\n", "", "NFR-1 must have Status, Done")

    def test_each_required_test_type_has_a_test_or_an_open_proof_item(self):
        self.fails_with("  - api: `test_api`, `tests/test_pricing.py:5`\n", "", "AC-2 has no api test, nor the OP-n")
        self.claims = CLAIMS
        self.fails_with("performance: OP-1", "performance: OP-2", "names an OP-n that Open proof items")
        self.claims = CLAIMS
        self.fails_with("performance: OP-1", "performance: on staging", "give the test with `path:line`")
        self.claims = CLAIMS
        self.fails_with("- **Status:** not verified", "- **Status:** met", "NFR-1 is `met`, but OP-1 stands in")

    def test_an_indented_code_block_is_output(self):
        self.claims = CLAIMS.replace("```text\nRan 2 tests in 0.001s\nOK\n```", "  ```text\nRan 2 tests\n  ```")
        self.assertEqual(self.run_check()[0], 0)

    def test_a_test_type_continues_on_the_next_line(self):
        code, out = self.run_check()
        self.assertNotIn("AC-2, unit", out)
        self.fails_with("- **Test types:**\n  - unit: `test_negative`",
                        "- **Evidence:** x\n  - unit: `test_negative`", "a test type outside **Test types**")

    def test_open_proof_items_are_numbered_and_complete(self):
        self.fails_with("- **Owner:** not named\n", "", "OP-1 must have Unproven, Proof, Owner")
        self.claims = CLAIMS.replace("### OP-1", "### OP-2").replace("OP-1", "OP-2")
        self.assertIn("numbered OP-1, OP-2", self.run_check()[1])
        self.claims = CLAIMS.replace("### OP-1\n\n- **Unproven:** NFR-1, performance.\n- **Proof:** the nightly "
                                     "load run on staging.\n- **Owner:** not named\n", "None.\n")
        self.assertIn("names an OP-n that Open proof items does not define", self.run_check()[1])

    def test_files_changed_holds_true_line_counts(self):
        self.fails_with("(3 lines)", "(4 lines)", "`src/pricing.py` has 3 lines, not 4")
        self.claims = CLAIMS
        self.write("src/old.py", "")
        self.fails_with("(3 lines)", "(3 lines)", "`src/old.py` is marked deleted, but it exists")
        self.claims = CLAIMS
        self.fails_with("- `src/pricing.py`", "- `src/gone.py`", "`src/gone.py` does not exist")
        self.claims = CLAIMS
        self.fails_with("- `src/pricing.py`", "- `../pricing.py`", "a path from the project root")

    def test_references_name_lines_that_exist(self):
        self.fails_with("`tests/test_pricing.py:5`", "`tests/test_pricing.py:9`", "the file has 5 lines")
        self.claims = CLAIMS
        self.fails_with("`src/pricing.py:1-3`", "`src/pricing.py:1-4`", "the file has 3 lines")
        self.claims = CLAIMS
        self.fails_with("`src/pricing.py:2`", "`src/missing.py:2`", "`src/missing.py:2`: no such file")

    def test_the_story_frontmatter(self):
        self.write(".harness/runs/r1/stories/S01.md", "## What\n\nNo frontmatter.\n")
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("not checked: requirements against the story", out)
        self.write(".harness/runs/r1/stories/S01.md", STORY.replace(
            "tests: {AC-1: [unit], AC-2: [unit, api], NFR-1: [performance]}", "tests:\n  AC-1: [unit]"))
        code, out = self.run_check()
        self.assertEqual(code, 2, out)
        self.assertIn("flow form", out)
        self.assertEqual(self.run_check("--story", "missing.md")[0], 2)

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_files_changed_equals_the_change(self):
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        self.write("src/old.py", "x\n")
        subprocess.run([*git, "init", "-q"], cwd=self.repo, check=True)
        subprocess.run([*git, "add", "."], cwd=self.repo, check=True)
        subprocess.run([*git, "commit", "-qm", "base"], cwd=self.repo, check=True)
        (self.repo / "src/old.py").unlink()
        self.write("src/pricing.py", "a\nb\nC\n")
        self.write("src/new.py", "n\n")
        code, out = self.run_check("--base", "HEAD")
        self.assertEqual(code, 1, out)
        self.assertIn("`src/new.py` changed since HEAD, but Files changed does not list it", out)
        self.assertNotIn("`.harness", out)  # the run folder is not part of the change
        self.claims = CLAIMS.replace("- `src/old.py` (deleted)", "- `src/old.py` (deleted)\n- `src/new.py` (1 line)")
        self.assertEqual(self.run_check("--base", "HEAD")[0], 0)
        self.claims = self.claims.replace("(1 line)", "(1 line)\n- `tests/test_pricing.py` (5 lines)")
        self.assertIn("did not change since HEAD", self.run_check("--base", "HEAD")[1])


if __name__ == "__main__":
    unittest.main()
