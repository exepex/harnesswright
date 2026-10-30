"""Tests for skills/claims-writer/scripts/claims_check.py. Run from the repository root:
python3 -m unittest discover -s evals/skills/claims-writer/tests
"""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "skills" / "claims-writer" / "scripts"))
import claims_check  # noqa: E402

STORY = """---
id: S01
---

## Acceptance criteria

- AC-1: Discount at 100.00.
- AC-2: Negative quantity raises.

## Out of scope

AC-9 is mentioned here but is not a criterion.
"""


def claims(requirements, files="- `src/a.py` (2 lines)\n- `Makefile` (1 line)", extra=""):
    return f"""# Claims · S01

## Request

> Give a discount.

## Requirements

{requirements}

## Standards

None resolved for this repository.

## Out of scope

None.

## Files changed

{files}

## Not verified

None.
{extra}"""


def entry(ac, status="met", ref="`src/a.py:2`"):
    return f"### AC-{ac} · x\n- **Status:** {status}\n- **Done:** {ref}\n- **Evidence:** ran tests, exit code 0\n"


class ClaimsCheckTest(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        (self.repo / "src").mkdir()
        (self.repo / "src" / "a.py").write_text("x = 1\ny = 2\n")
        (self.repo / "Makefile").write_text("test:\n")
        run = self.repo / ".harness" / "runs" / "r1"
        (run / "stories").mkdir(parents=True)
        (run / "claims").mkdir()
        (run / "stories" / "S01.md").write_text(STORY)
        self.claims = run / "claims" / "S01.md"

    def check(self, text, *extra):
        self.claims.write_text(text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = claims_check.main(["check", "--repo", str(self.repo), *extra, str(self.claims)])
        return code, out.getvalue()

    def test_complete_claims_pass(self):
        code, out = self.check(claims(entry(1) + entry(2, "not verified")))
        self.assertEqual(code, 0, out)

    def test_missing_criterion_is_reported(self):
        code, out = self.check(claims(entry(1)))
        self.assertEqual(code, 1)
        self.assertIn("AC-2 of the story has no entry", out)

    def test_criterion_not_in_story_and_duplicates_are_reported(self):
        code, out = self.check(claims(entry(1) + entry(2) + entry(2) + entry(9)))
        self.assertIn("AC-2 has more than one entry", out)
        self.assertIn("AC-9 is not in the story", out)

    def test_invalid_or_missing_status_is_reported(self):
        code, out = self.check(claims(entry(1, "done") + "### AC-2 · y\n- **Done:** x\n"))
        self.assertIn("Status 'done'", out)
        self.assertIn("'AC-2 · y' needs exactly one **Status:** line", out)

    def test_extensionless_reference_is_checked_when_the_file_exists(self):
        code, out = self.check(claims(entry(1, ref="`Makefile:3`") + entry(2)))
        self.assertIn("reference `Makefile:3`: file has 1 lines", out)
        code, out = self.check(claims(entry(1, ref="`localhost:8080`") + entry(2)))
        self.assertEqual(code, 0, out)

    def test_missing_file_with_extension_is_reported(self):
        code, out = self.check(claims(entry(1, ref="`src/b.py:1`") + entry(2)))
        self.assertIn("reference `src/b.py:1`: file not found", out)

    def test_without_a_story_mapping_is_skipped_with_a_note(self):
        (self.claims.parent.parent / "stories" / "S01.md").unlink()
        code, out = self.check(claims(entry(1)))
        self.assertEqual(code, 0, out)
        self.assertIn("note: no story file found", out)

    def test_files_changed_must_match_the_diff(self):
        def git(*args):
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=self.repo,
                           check=True, capture_output=True)
        git("init", "-q")
        git("add", "src", "Makefile")
        git("commit", "-qm", "base")
        (self.repo / "src" / "a.py").write_text("x = 1\ny = 3\n")
        (self.repo / "src" / "new.py").write_text("z = 1\n")
        code, out = self.check(claims(entry(1) + entry(2)), "--base", "HEAD")
        self.assertIn("src/new.py changed since HEAD but is not listed", out)
        self.assertIn("Makefile is listed but did not change since HEAD", out)
        self.assertNotIn("src/a.py", out)


if __name__ == "__main__":
    unittest.main()
