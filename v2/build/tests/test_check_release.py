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
            if build.is_copy(rel):
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

    def test_the_copied_layers_and_roles_file_are_not_skills_and_must_equal_their_sources(self):
        self.assertTrue((self.release / "rules/core/test.md").is_file())
        self.assertNoFailure("release/rules: has no SKILL.md")
        self.edit("release/rules/core/test.md", "Name each test", "Name every test")
        self.assertFails("release/rules/core/test.md: differs from a rebuild")
        self.setUp()
        self.edit("release/roles.md", "| Role |", "| Roles |")
        self.assertFails("release/roles.md: differs from a rebuild")

    def test_a_source_the_build_rejects_fails(self):
        with open(self.root / "v2/skills/golden-skill/SKILL.tmpl.md", "a", encoding="utf-8") as handle:
            handle.write("4. See CORE-TEST-09.\n")
        self.assertFails("build.py: the rebuild failed")

    def test_body_lines_like_generated_metadata_or_sub_headings_are_counted(self):
        with open(self.root / "v2/skills/golden-skill/SKILL.tmpl.md", "a", encoding="utf-8") as handle:
            handle.write('\n```yaml\nmetadata:\n  size-rest: "123"\n```\n')
        self.edit("root/v2/rules/core/work.md", "know how you know it.",
                  "know how you know it, up to `### Other rules`.")
        shutil.rmtree(self.release)
        build.write(self.release, build.build(self.root))
        self.assertEqual(self.check()[0], [])

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
                  "<!-- rule CORE-TEST-04 -->", "block JAVA-TEST-01: copies a rule that is not an active CORE rule"),
                 (SKILL, "<!-- rule CORE-TEST-04 -->", "<!-- rule CORE-TEST-02 -->\n<!-- end CORE-TEST-02 -->\n"
                  "<!-- rule CORE-TEST-04 -->", "block CORE-TEST-02: copies a rule that is not an active CORE rule"),
                 (SKILL, "outcome per case\n\n- **Kind:**", "outcome per case\n- **Kind:**",
                  "block CORE-TEST-04: does not start with the heading"),
                 (SKILL, "two outcomes.\n<!-- end CORE-TEST-04 -->", "two outcomes.\nExtra.\n<!-- end CORE-TEST-04 -->",
                  "block CORE-TEST-04: holds other text"),
                 (SKILL, "- **Rule:** Each test checks one behaviour.",
                  "- **Rule:** Tests may check many.\n- **Rule:** Each test checks one behaviour.",
                  "block CORE-TEST-011: holds other text"),
                 (SKILL, "- **Good:** One test for the low-stock case, one for the enough-stock case.\n"
                  "- **Bad (do not do this):** One test that asserts both cases.",
                  "- **Bad (do not do this):** One test that asserts both cases.\n"
                  "- **Good:** One test for the low-stock case, one for the enough-stock case.",
                  "block CORE-TEST-011: holds the parts"),
                 (SKILL, "  void rejectsOrderWhenStockIsLow() {}", "  void rejectsOrderWhenStockIsLow() {} ",
                  "block CORE-TEST-01: its Good differs"),
                 (SKILL, "<!-- end CORE-TEST-04 -->", "<!-- end CORE-TEST-05 -->",
                  "block CORE-TEST-04 has no end marker of its own")]
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
                 ("size-rest", 5, "golden-skill size-rest is '5'"),
                 ("size-floors", 5, "golden-skill size-floors is '5'"),
                 ("rulebook-version", "0.0.1", "golden-skill rulebook-version is '0.0.1'")]
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
        self.edit(SKILL, 'size-floors: "284"', 'size-floors: "30001"')
        self.assertFails("size-floors is 30001, over the ceiling of 30000")
        self.setUp()
        self.edit(SKILL, 'size-rest: "2056"', 'size-rest: "30000"')
        self.assertNoFailure("over the ceiling")

    def test_a_skill_md_outside_the_agent_skills_format_fails(self):
        cases = [("name: golden-skill", "name: Golden-Skill", "name 'Golden-Skill' must equal the folder name"),
                 ("name: golden-skill", "name: other-skill", "name 'other-skill' must equal the folder name"),
                 ("description: Golden fixture", "description: Golden < fixture", "description must be"),
                 ("description: Golden fixture", "description: Golden > fixture", "description must be"),
                 ("description: Golden fixture for the build tests. Never used as a real skill.",
                  "description: " + "x" * 1025, "description must be"),
                 ("description: Golden fixture for the build tests. Never used as a real skill.", "description: ''",
                  "description must be"),
                 ("name: golden-skill", "name: golden-skill\nBad line", "frontmatter line has no allowed shape"),
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

    def test_the_skill_text_is_recounted_and_the_skill_md_has_no_line_limit(self):
        self.edit(SKILL, "1. Keep each test", "1. Always keep each test")
        self.assertFails("metadata.content-hash is")
        self.assertFails("metadata.size-rest is '2056'; its text gives '2063'")
        self.setUp()
        with open(self.release / "golden-skill/SKILL.md", "a", encoding="utf-8") as handle:
            handle.write("More.\n" * 500)
        self.assertNoFailure("over 500")

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
        self.setUp()
        (self.root / "v2/skills/golden-skill/references/SKILL.md").write_text("Line.\n" * 501, encoding="utf-8")
        build.write(self.release, build.build(self.root))
        self.assertFails("references/SKILL.md: has 503 lines, over 500")

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
            "size-floors 500 -> 284; size-rest 2056 -> 2056; FLOOR REMOVED: CORE-WORK-02; FLOORS SHRANK",
            "old-skill: removed skill; added none; removed none; size-floors 1 -> 0; size-rest 2 -> 0; FLOORS SHRANK"])
        entry["copied-ids"], entry["size-floors"] = manifest["skills"]["golden-skill"]["copied-ids"], 285
        del base["skills"]["old-skill"]
        summary = self.check(base)[1]
        self.assertTrue(summary[0].endswith("size-floors 285 -> 284; size-rest 2056 -> 2056; FLOORS SHRANK"), summary)
        entry["size-floors"], entry["content-hash"] = 284, "0" * 64
        self.assertEqual(self.check(base)[1], [
            "golden-skill: changed; added none; removed none; size-floors 284 -> 284; size-rest 2056 -> 2056"])

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
