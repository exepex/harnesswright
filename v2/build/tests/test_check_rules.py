"""Tests for check_rules.py. Run: python3 -m unittest discover -s v2/build/tests

Each test starts from a copy of the golden fixture (golden/root and its hand-written release golden/expected), which
passes, and breaks one thing.
"""

import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import check_rules  # noqa: E402

GOLDEN = HERE / "golden"
REPO = HERE.parents[2]
# The required parts, written out from docs/design/03-standards.md, not read from the check.
RULE_PARTS = ("Kind", "Status", "Review by", "Applies to", "Rule", "Why", "Check", "Good", "Bad", "Eval", "Source")
POINT_PARTS = ("Status", "Review by", "Question", "Options", "Default", "Why", "Applies to", "Source")


class CheckRulesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root, self.release = self.tmp / "root", self.tmp / "release"
        shutil.copytree(GOLDEN / "root", self.root)
        shutil.copytree(GOLDEN / "expected", self.release)

    def edit(self, path, old, new):
        path = self.tmp / path
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(old), 1, f"{old!r} must occur once in {path}")
        path.write_text(text.replace(old, new), encoding="utf-8")

    def check(self, changed=None, jobs=()):
        return check_rules.Check(self.root, self.release).run(changed, jobs)

    def assertFails(self, expected, **kwargs):
        failures = self.check(**kwargs)
        self.assertTrue(any(expected in failure for failure in failures), failures)

    def test_the_golden_fixture_and_the_repository_pass(self):
        self.assertEqual(self.check(jobs=["golden"]), [])
        self.assertEqual(check_rules.Check(REPO, REPO / "release").run(), [])

    def drop_part(self, path, heading, part):
        """Remove one part, with its continuation lines, from the rule under heading."""
        path = self.root / path
        lines = path.read_text(encoding="utf-8").split("\n")
        start = next(i for i in range(lines.index(heading), len(lines)) if lines[i].startswith(f"- **{part}:**"))
        end = next(i for i in range(start + 1, len(lines)) if not lines[i].startswith("  "))
        path.write_text("\n".join(lines[:start] + lines[end:]), encoding="utf-8")

    def test_a_rule_or_decision_point_missing_any_part_fails(self):
        cases = [("v2/rules/core/test.md", "### CORE-TEST-01 · A test names its scenario", "CORE-TEST-01", RULE_PARTS),
                 ("v2/rules/core/dp.md", "### CORE-DP-NAMES · How tests are named", "CORE-DP-NAMES", POINT_PARTS)]
        for path, heading, rule_id, parts in cases:
            for part in parts:
                with self.subTest(rule=rule_id, part=part):
                    self.setUp()
                    self.drop_part(path, heading, part)
                    self.assertFails(f"{rule_id} has no {part}")

    def test_a_part_twice_a_bad_status_or_kind_or_a_rule_defined_twice_fails(self):
        cases = [("- **Why:** Slow tests are skipped.", "- **Why:** Slow tests are skipped.\n- **Why:** Again.",
                  "CORE-TEST-02 has Why twice"),
                 ("- **Status:** inferred", "- **Status:** Active", "CORE-TEST-02 has Status 'Active'"),
                 ("- **Status:** inferred\n", "- **Status:** inferred\n- **Kind:** rule\n", "CORE-TEST-02 has Kind twice"),
                 ("### CORE-TEST-02 · A test runs", "### CORE-TEST-01 · A test runs", "CORE-TEST-01 is already defined")]
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit("root/v2/rules/core/test.md", old, new)
                self.assertFails(expected)
        self.setUp()
        self.edit("root/v2/rules/core/test.md", "- **Kind:** principle\n- **Status:** inferred",
                  "- **Kind:** rule\n- **Status:** inferred")
        self.assertFails("CORE-TEST-02 has Kind 'rule'")

    def test_a_retired_rule_without_its_replacement_fails(self):
        self.edit("root/v2/rules/core/retired.md", "- **Replaced by:** CORE-TEST-01\n", "")
        self.assertFails("CORE-TEST-03 has no Replaced by")

    def test_an_unknown_role_fails(self):
        self.edit("root/v2/rules/core/test.md", "- **Applies to:** reviewer\n- **Rule:** Each test checks",
                  "- **Applies to:** reviewer, auditor\n- **Rule:** Each test checks")
        self.assertFails("CORE-TEST-011 applies to unknown role 'auditor'")
        self.edit("root/v2/skills/golden-skill/SKILL.tmpl.md", "roles: tester", "roles: testers")
        self.assertFails("metadata.roles names unknown role 'testers'")

    def test_a_copy_marker_fails_in_rule_files_and_skill_folders(self):
        cases = [("root/v2/rules/core/work.md", "<!-- rule CORE-WORK-01 -->"),
                 ("root/v2/rules/java/test.md", "## Rules for this skill"),
                 ("root/v2/skills/golden-skill/SKILL.tmpl.md", "<!-- end CORE-TEST-01 -->"),
                 ("root/v2/skills/golden-skill/references/guide.md", "<!-- Generated from x at version 1. -->")]
        for path, marker in cases:
            with self.subTest(path=path):
                self.setUp()
                with open(self.tmp / path, "a", encoding="utf-8") as handle:
                    handle.write(f"\n{marker}\n")
                self.assertFails("holds a copy marker")

    def test_the_index_and_readme_of_a_layer_are_not_rule_files(self):
        for name in ("index.md", "README.md"):
            (self.root / "v2/rules/core" / name).write_text("# Notes\n\n### CORE-TEST-99 · Not a rule\n",
                                                             encoding="utf-8")
        self.assertEqual(self.check(), [])

    def test_a_template_named_skill_md_fails(self):
        shutil.copy(self.root / "v2/skills/golden-skill/SKILL.tmpl.md", self.root / "v2/skills/golden-skill/SKILL.md")
        self.assertFails("never SKILL.md")

    def test_a_cited_id_that_is_unknown_retired_or_inferred_fails(self):
        cases = [("CORE-TEST-09", "unknown"), ("CORE-TEST-03", "retired"), ("CORE-TEST-02", "inferred"),
                 ("JAVA-TEST-01", "unknown")]
        for rule_id, status in cases:
            for path in ("SKILL.tmpl.md", "references/guide.md"):
                with self.subTest(rule=rule_id, path=path):
                    self.setUp()
                    with open(self.root / "v2/skills/golden-skill" / path, "a", encoding="utf-8") as handle:
                        handle.write(f"\nSee {rule_id}.\n")
                    self.assertFails(f"golden-skill/{path}: cites {rule_id}, which is {status}")

    def test_jobs_that_do_not_match_the_skill_folders_fail(self):
        row = "| golden | tester | golden-skill | golden-skill |"
        cases = [(row, "| golden | tester | golden-skill, other | golden-skill |", "names other, which has no"),
                 (row, "| golden | reviewer | golden-skill | golden-skill |", "not the job's reviewer"),
                 (row, row + "\n| second | tester | golden-skill | golden-skill |", "which job golden also names"),
                 (row, "| golden | tester | other | other |", "golden-skill: is in no job"),
                 (row, "| golden | tester, reviewer | golden-skill | golden-skill |", "not the job's tester, reviewer"),
                 (row, row + "\n| golden | tester | golden-skill | golden-skill |", "job golden is listed twice")]
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit("root/v2/roles.md", old, new)
                self.assertFails(expected)
        self.setUp()
        self.edit("root/v2/skills/golden-skill/SKILL.tmpl.md", "roles: tester", "roles: tester, reviewer")
        self.assertFails("golden-skill has roles ['tester', 'reviewer'], not the job's tester")

    def test_a_line_with_no_allowed_shape_or_a_row_of_the_wrong_width_fails(self):
        cases = [("root/v2/rules/core/work.md", "### CORE-WORK-01 · Report only what you verified",
                  "### CORE-WORK-01 - Report only what you verified", "work.md:5: line has no allowed shape"),
                 ("root/v2/rules/core/test.md", "Golden fixture for the build tests.",
                  "- **Kind:** floor", "test.md:3: line has no allowed shape"),
                 ("root/v2/rules/core/test.md", "- **Why:** A failing test should say what broke.",
                  "- **Why:** A failing test should say what broke.\nSee also the guide.", "line has no allowed shape"),
                 ("root/v2/roles.md", "| golden | tester | golden-skill | golden-skill |",
                  "| golden | tester | golden-skill | golden-skill |\n  | broken | tester | none | none |",
                  "line has no allowed shape under '## Jobs'"),
                 ("root/v2/roles.md", "| golden | tester | golden-skill | golden-skill |",
                  "| golden | tester | golden-skill | golden-skill |\n\n| broken | tester | none | none |",
                  "line has no allowed shape under '## Jobs'"),
                 ("root/v2/roles.md", "| golden | tester | golden-skill | golden-skill |",
                  "| golden | tester | golden-skill | golden-skill |\n| broken | tester | none | none | extra |",
                  "row needs 4 cells under '## Jobs'"),
                 ("root/v2/roles.md", "| reviewer | checking |", "| reviewer | checking | extra |",
                  "row needs 7 cells under '## Roles'"),
                 ("root/v2/roles.md", "|---|---|---|---|\n| golden", "| bad | tester | none | none |\n| golden",
                  "the table under '## Jobs' needs a header row and a rule line"),
                 ("root/v2/skills/golden-skill/SKILL.tmpl.md", "  areas: rest", "  areas: rest\n   roles: x",
                  "SKILL.tmpl.md:7: frontmatter line has no allowed shape"),
                 ("root/v2/skills/golden-skill/SKILL.tmpl.md", "  roles: tester", "  roles: reviewer\n  roles: tester",
                  "SKILL.tmpl.md:6: frontmatter line has no allowed shape or repeats a key"),
                 ("root/v2/roles.md", "| golden | tester | golden-skill | golden-skill |",
                  "| golden | tester | golden-skill | golden-skill |\nMore jobs come later.", "under '## Jobs'")]
        for path, old, new, expected in cases:
            with self.subTest(expected=expected, new=new):
                self.setUp()
                self.edit(path, old, new)
                self.assertFails(expected)

    def test_a_job_with_two_rest_skills_fails(self):
        other = self.root / "v2/skills/other-skill"
        other.mkdir()
        (other / "SKILL.tmpl.md").write_text("---\nname: other-skill\ndescription: Another.\nmetadata:\n"
                                             "  roles: tester\n  areas: rest\n---\n\n# Other\n", encoding="utf-8")
        self.edit("root/v2/roles.md", "| tester | golden-skill |", "| tester | other-skill, golden-skill |")
        self.assertFails("its `rest` skill is golden-skill, but the templates mark ['other-skill', 'golden-skill']")

    def test_a_job_without_its_rest_skill_fails(self):
        self.edit("root/v2/skills/golden-skill/SKILL.tmpl.md", "areas: rest", "areas: TEST")
        self.assertFails("its `rest` skill is golden-skill, but the templates mark none")

    def test_a_release_missing_a_floor_or_an_area_rule_fails(self):
        cases = [("<!-- rule CORE-WORK-01 -->", "misses CORE-WORK-01, which applies to every role"),
                 ("<!-- rule CORE-TEST-01 -->", "misses CORE-TEST-01 of area TEST")]
        for marker, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit("release/golden-skill/SKILL.md", marker + "\n", "")
                self.assertFails(expected)
        self.setUp()
        self.edit("root/v2/rules/core/work.md", "- **Applies to:** reviewer", "- **Applies to:** reviewer, tester")
        self.assertFails("misses floor CORE-WORK-02")

    def test_the_rest_skill_leaves_out_areas_another_skill_of_its_job_lists(self):
        other = self.root / "v2/skills/other-skill"
        other.mkdir()
        (other / "SKILL.tmpl.md").write_text("---\nname: other-skill\ndescription: Another.\nmetadata:\n"
                                             "  roles: tester\n  areas: TEST\n---\n\n# Other\n", encoding="utf-8")
        (self.release / "other-skill").mkdir()
        (self.release / "other-skill/SKILL.md").write_text(
            "<!-- rule CORE-WORK-01 -->\n<!-- rule CORE-TEST-01 -->\n", encoding="utf-8")
        self.edit("root/v2/roles.md", "| tester | golden-skill |", "| tester | other-skill, golden-skill |")
        skill = self.release / "golden-skill/SKILL.md"
        text = skill.read_text(encoding="utf-8")
        start, end = text.index("<!-- rule CORE-TEST-01 -->"), text.index("<!-- end CORE-TEST-01 -->\n\n")
        skill.write_text(text[:start] + text[end + len("<!-- end CORE-TEST-01 -->\n\n"):], encoding="utf-8")
        self.assertEqual(self.check(), [])
        self.edit("release/other-skill/SKILL.md", "<!-- rule CORE-TEST-01 -->\n", "")
        self.assertFails("other-skill/SKILL.md: misses CORE-TEST-01 of area TEST")

    def test_a_decision_point_that_is_not_cited_need_not_be_copied(self):
        self.edit("root/v2/rules/core/dp.md", "- **Applies to:** tester", "- **Applies to:** every role")
        self.assertEqual(self.check(), [])

    def test_a_missing_release_fails(self):
        shutil.rmtree(self.release / "golden-skill")
        self.assertFails("release/golden-skill: has no SKILL.md")

    def test_a_bare_or_unknown_id_in_a_release_fails(self):
        self.edit("release/golden-skill/SKILL.md", "CORE-TEST-011 (A test checks one behaviour) says",
                  "CORE-TEST-011 says")
        self.assertFails("SKILL.md:79: CORE-TEST-011 is bare")
        self.setUp()
        self.edit("release/golden-skill/references/guide.md", "(A test names its scenario)", "(Wrong title)")
        self.assertFails("references/guide.md:3: CORE-TEST-01 is bare")
        self.setUp()
        with open(self.release / "golden-skill/SKILL.md", "a", encoding="utf-8") as handle:
            handle.write("See CORE-TEST-09 (Nothing) and JAVA-TEST-01 (Use AssertJ).\n")
        self.assertFails("CORE-TEST-09 is not in the CORE rulebook")
        self.assertFails("JAVA-TEST-01 is not in the CORE rulebook")

    def test_an_id_inside_a_checked_title_is_not_a_citation(self):
        self.edit("root/v2/rules/core/test.md", "### CORE-TEST-01 · A test names its scenario",
                  "### CORE-TEST-01 · A test follows CORE-WORK-01")
        self.edit("release/golden-skill/references/guide.md", "(A test names its scenario)",
                  "(A test follows CORE-WORK-01)")
        self.assertFalse([f for f in self.check() if "guide.md" in f], self.check())

    def test_ids_inside_copied_blocks_and_file_names_are_not_citations(self):
        self.edit("release/golden-skill/SKILL.md", "<!-- end CORE-TEST-04 -->",
                  "See CORE-TEST-011 and CORE-TEST-09.\n<!-- end CORE-TEST-04 -->")
        with open(self.release / "golden-skill/SKILL.md", "a", encoding="utf-8") as handle:
            handle.write("Files: `CORE-TEST-09.md`, rules/CORE-TEST-09, x-CORE-TEST-09.\n")
        self.assertEqual(self.check(), [])

    def test_an_unknown_job_fails(self):
        self.assertFails("unknown job 'gold'", jobs=["golden", "gold"])

    def test_a_rule_file_changed_without_a_version_bump_fails(self):
        self.assertFails("a rule file changed but v2/VERSION did not", changed=["v2/rules/core/test.md"])
        for changed in (["v2/rules/core/test.md", "v2/VERSION"], ["v2/rules/core/index.md", "v2/build/x.py"]):
            with self.subTest(changed=changed):
                self.assertEqual(self.check(changed=changed), [])

    def test_the_command_line_prints_each_failure_and_returns_1(self):
        changed = self.tmp / "changed.txt"
        changed.write_text("v2/rules/core/test.md\n", encoding="utf-8")
        args = ["--root", str(self.root), "--release", str(self.release)]
        self.assertEqual(check_rules.main(args), 0)
        err = io.StringIO()
        with redirect_stderr(err):
            code = check_rules.main(args + ["--changed", str(changed), "--job", "gold"])
        self.assertEqual(code, 1)
        self.assertEqual(err.getvalue().splitlines(), [
            "check failed: --job: unknown job 'gold'",
            "check failed: v2/rules/core/test.md: a rule file changed but v2/VERSION did not"])

    def test_an_unreadable_input_fails_without_a_traceback(self):
        (self.root / "v2/roles.md").unlink()
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(check_rules.main(["--root", str(self.root), "--release", str(self.release)]), 1)
        self.assertIn("check failed: cannot read:", err.getvalue())


if __name__ == "__main__":
    unittest.main()
