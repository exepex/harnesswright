"""Tests for check_release.py. Run: python3 -m unittest discover -s v2/build/tests

Each test starts from the golden fixture: golden/root as the sources, and the hand-written golden/expected plus the
shipped scripts as release/, which passes. Then it breaks one thing.
"""

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import build  # noqa: E402
import check_release  # noqa: E402

GOLDEN = HERE / "golden"
REPO = HERE.parents[2]
SKILL = "release/golden-skill/SKILL.md"


class CheckReleaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root, self.release = self.tmp / "root", self.tmp / "release"
        shutil.copytree(GOLDEN / "root", self.root)
        shutil.copytree(GOLDEN / "expected", self.release)
        for rel, data in build.build(self.root).items():
            if "/scripts/" in rel:
                (self.release / rel).parent.mkdir(parents=True, exist_ok=True)
                (self.release / rel).write_bytes(data)

    def edit(self, path, old, new):
        path = self.tmp / path
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(old), 1, f"{old!r} must occur once in {path}")
        path.write_text(text.replace(old, new), encoding="utf-8")

    def check(self, base=None):
        return check_release.ReleaseCheck(self.root, self.release).run(base)

    def assertFails(self, expected):
        failures = self.check()[0]
        self.assertTrue(any(expected in failure for failure in failures), failures)

    def assertNoFailure(self, text):
        failures = self.check()[0]
        self.assertFalse([f for f in failures if text in f], failures)

    def test_the_golden_release_and_the_repository_pass(self):
        self.assertEqual(self.check(), ([], []))
        self.assertEqual(check_release.ReleaseCheck(REPO, REPO / "release").run(), ([], []))

    def test_a_release_that_is_not_a_rebuild_fails(self):
        self.edit(SKILL, "1. Keep each test", "1. Always keep each test")
        self.assertFails("SKILL.md: differs from a rebuild")
        self.setUp()
        (self.release / "golden-skill/references/guide.md").unlink()
        self.assertFails("references/guide.md: is missing")
        self.setUp()
        (self.release / "golden-skill/notes.md").write_text("Hand-written.\n", encoding="utf-8")
        self.assertFails("golden-skill/notes.md: is not made by the build")

    def test_a_source_the_build_rejects_fails(self):
        with open(self.root / "v2/skills/golden-skill/SKILL.tmpl.md", "a", encoding="utf-8") as handle:
            handle.write("4. See CORE-TEST-09.\n")
        self.assertFails("build.py: the rebuild failed")

    def test_a_copied_block_that_differs_from_its_rule_fails(self):
        cases = [("root/v2/rules/core/test.md", "- **Rule:** Each test checks one behaviour.",
                  "- **Rule:** Each test checks one or two behaviours.", "block CORE-TEST-011: its Rule differs"),
                 (SKILL, "  void acceptsOrderWhenStockIsEnough() {}", "  void acceptsOrderWhenStockIsEnough()  {}",
                  "block CORE-TEST-01: its Good differs"),
                 (SKILL, "#### CORE-TEST-04 · A test checks one outcome per case", "#### CORE-TEST-04 · Other",
                  "block CORE-TEST-04: does not start with the heading"),
                 (SKILL, "- **Exceptions:** generated tests,\n  and tests copied unchanged from a vendor.\n", "",
                  "block CORE-TEST-01: holds the parts"),
                 (SKILL, "\nThe binding in your rules text wins; the default applies only when unbound.", "",
                  "block CORE-DP-NAMES: holds other text"),
                 (SKILL, "<!-- rule CORE-TEST-04 -->", "<!-- rule CORE-TEST-03 -->\n#### CORE-TEST-03 · x\n"
                  "<!-- end CORE-TEST-03 -->\n<!-- rule CORE-TEST-04 -->",
                  "block CORE-TEST-03: copies a rule that is not an"),
                 (SKILL, "<!-- rule CORE-TEST-04 -->", "<!-- rule JAVA-TEST-01 -->\n<!-- end JAVA-TEST-01 -->\n"
                  "<!-- rule CORE-TEST-04 -->", "block JAVA-TEST-01: copies a rule that is not an active CORE rule")]
        for path, old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit(path, old, new)
                self.assertFails(expected)

    def test_prose_is_compared_with_whitespace_collapsed(self):
        self.edit(SKILL, "- **Rule:** Name each test after the situation it sets up\n  and the result it expects.",
                  "- **Rule:** Name each test after the situation\n  it sets up and the  result it expects.")
        self.assertNoFailure("differs from the rule")
        self.assertFails("SKILL.md: differs from a rebuild")

    def test_a_manifest_that_disagrees_with_its_skills_fails(self):
        manifest = self.release / "manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        cases = [("content-hash", "0" * 64, "golden-skill content-hash is"),
                 ("copied-ids", ["CORE-WORK-01"], "golden-skill copied-ids is 'CORE-WORK-01'"),
                 ("size-rest", 5, "golden-skill size-rest is '5'")]
        for key, value, expected in cases:
            with self.subTest(key=key):
                self.setUp()
                changed = json.loads(json.dumps(data))
                changed["skills"]["golden-skill"][key] = value
                (self.release / "manifest.json").write_text(json.dumps(changed), encoding="utf-8")
                self.assertFails(expected)
        self.setUp()
        (self.release / "manifest.json").write_text(json.dumps({"skills": {}}), encoding="utf-8")
        self.assertFails("lists [], not the skills ['golden-skill']")

    def test_metadata_that_disagrees_with_the_skill_text_fails(self):
        cases = [('size-floors: "284"', 'size-floors: "283"', "metadata.size-floors is '283'; its text gives '284'"),
                 ('rulebook-version: "0.3.1"', 'rulebook-version: "0.3.0"', "metadata.rulebook-version is '0.3.0'"),
                 ("CORE-TEST-011, CORE-TEST-04\"", "CORE-TEST-04, CORE-TEST-011\"", "metadata.copied-ids is")]
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit(SKILL, old, new)
                self.assertFails(expected)

    def test_recorded_sizes_over_the_ceiling_fail(self):
        self.edit(SKILL, 'size-rest: "2056"', 'size-rest: "30001"')
        self.assertFails("size-rest is 30001, over the ceiling of 30000")
        self.setUp()
        self.edit(SKILL, 'size-rest: "2056"', 'size-rest: "30000"')
        self.assertNoFailure("over the ceiling")

    def test_a_skill_md_outside_the_agent_skills_format_fails(self):
        cases = [("name: golden-skill", "name: Golden-Skill", "name 'Golden-Skill' must equal the folder name"),
                 ("name: golden-skill", "name: other-skill", "name 'other-skill' must equal the folder name"),
                 ("description: Golden fixture", "description: Golden < fixture", "description must be"),
                 ("name: golden-skill", "name: golden-skill\nallowed-tools: Bash", "field 'allowed-tools' is not"),
                 ("description: Golden fixture", "description: <b>Golden</b> fixture", "description must be"),
                 ("description: Golden fixture", "compatibility: " + "x" * 501 + "\ndescription: Golden fixture",
                  "compatibility is over 500 characters")]
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit(SKILL, old, new)
                self.assertFails(expected)

    def test_a_name_over_64_characters_fails(self):
        name = "a" * 65
        (self.release / name).mkdir()
        (self.release / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Long.\n---\n", encoding="utf-8")
        self.assertFails(f"name '{name}' must equal the folder name: at most 64")

    def test_an_expanded_reference_over_500_lines_fails_and_names_its_source(self):
        guide = self.release / "golden-skill/references/guide.md"
        lines = guide.read_text(encoding="utf-8").count("\n")
        with open(guide, "a", encoding="utf-8") as handle:
            handle.write("More.\n" * (500 - lines))
        self.assertNoFailure("over 500")
        with open(guide, "a", encoding="utf-8") as handle:
            handle.write("More.\n")
        self.assertFails("guide.md: has 501 lines, over 500; split its source "
                         "v2/skills/golden-skill/references/guide.md")

    def test_the_summary_lists_changes_and_flags_a_removed_floor(self):
        manifest = json.loads((self.release / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(self.check(manifest)[1], [])
        base = json.loads(json.dumps(manifest))
        entry = base["skills"]["golden-skill"]
        entry["copied-ids"] = ["CORE-WORK-02", "CORE-WORK-01", "CORE-TEST-02", "CORE-TEST-01"]
        entry["size-floors"] = 500
        base["skills"]["old-skill"] = {"copied-ids": [], "size-floors": 1, "size-rest": 2}
        self.assertEqual(self.check(base)[1], [
            "golden-skill: changed; added CORE-DP-NAMES, CORE-TEST-011, CORE-TEST-04; "
            "removed CORE-WORK-02, CORE-TEST-02; "
            "size-floors 500 -> 284; size-rest 2056 -> 2056; FLOOR REMOVED: CORE-WORK-02",
            "old-skill: removed skill; added none; removed none; size-floors 1 -> 0; size-rest 2 -> 0"])

    def test_the_command_line_prints_the_summary_and_each_failure(self):
        base = self.tmp / "base.json"
        base.write_text(json.dumps({"skills": {}}), encoding="utf-8")
        args = ["--root", str(self.root), "--release", str(self.release), "--base", str(base)]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(check_release.main(args), 0)
        self.assertTrue(out.getvalue().startswith("golden-skill: new skill; added CORE-WORK-01"), out.getvalue())
        self.assertEqual(err.getvalue(), "")
        self.edit(SKILL, "1. Keep each test", "1. Always keep each test")
        base.write_text("not json", encoding="utf-8")
        for given, expected in ((args[:4], "differs from a rebuild"), (args, "check failed: cannot read:")):
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                self.assertEqual(check_release.main(given), 1)
            self.assertIn(expected, err.getvalue())


if __name__ == "__main__":
    unittest.main()
