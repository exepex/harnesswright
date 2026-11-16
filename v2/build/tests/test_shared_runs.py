"""Tests for the skill designer's copy check, which ships in release/, so it is loaded by path.
Run: python3 -m unittest discover -s v2/build/tests"""

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "shared_runs", ROOT / "v2" / "skills" / "skill-designer" / "scripts" / "shared_runs.py")
shared_runs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shared_runs)

SOURCE = "4. Under **How to check it**, list the commands a reviewer runs, with what each should print.\n"


class SharedRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "src").mkdir()
        (self.tmp / "src" / "SKILL.md").write_text(SOURCE)

    def run_check(self, text, *extra):
        (self.tmp / "out.json").write_text(text)
        with redirect_stdout(io.StringIO()) as out:
            code = shared_runs.main(["--source", str(self.tmp / "src"), "--written", str(self.tmp / "out.json"),
                                     *extra])
        return code, out.getvalue()

    def test_a_run_split_by_a_comma_and_a_line_break_is_found_whole(self):
        code, out = self.run_check('"Does it List the commands a reviewer\\nruns with what each shows?"')
        self.assertEqual(code, 1)
        self.assertIn("list the commands a reviewer runs with what each\n", out)

    def test_a_json_file_is_read_with_its_escapes_decoded(self):
        source = "Each step \u2014 list the commands a reviewer runs, with what each should print.\n"
        (self.tmp / "src" / "SKILL.md").write_text(source)
        copied = json.dumps({"question": "Each step \u2014 list the commands a reviewer runs with what each shows?"})
        self.assertIn("\\u2014", copied)  # as json.dump writes it by default
        code, out = self.run_check(copied)
        self.assertEqual(code, 1)
        self.assertIn("each step list the commands a reviewer runs with what each\n", out)

    def test_seven_words_in_a_row_pass_and_a_lower_limit_finds_them(self):
        text = "open with list the commands a reviewer runs with, then stop."
        self.assertEqual(self.run_check(text)[0], 0)
        self.assertEqual(self.run_check(text, "--words", "7")[0], 1)

    def test_a_missing_path_is_an_input_error(self):
        with redirect_stdout(io.StringIO()):
            code = shared_runs.main(["--source", str(self.tmp / "none"), "--written", str(self.tmp)])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
