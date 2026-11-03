"""Tests for rulebook.py. Run from the repository root: python3 -m unittest discover -s v2/build/tests"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "v2" / "build"))

import rulebook  # noqa: E402

RULE = """### CORE-TEST-03 · A test name states the scenario and the expected outcome

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** implementer, test writer
- **Rule:** Name each test after the situation it sets up
  and the result it expects.
- **Why:** A failing test should say what broke.
- **Check:** Can I tell from the name what failed?
- **Good:** `rejectsOrderWhenStockIsInsufficient`
- **Bad:** `testOrder2`
- **Eval:** a test named `testOrder2`, which the reviewer must flag
- **Source:**
  - own (doc 03 example)
  - `a/b@1234567 c.md` (MIT)
"""

DECISION_POINT = """### CORE-DP-TEST-STACK · Which test tools a language uses

- **Status:** active
- **Review by:** 2027-11-03
- **Question:** Which test tools does this application use?
- **Options:**
  - `language-default`: the language layer's default test tools
  - `junit`: JUnit 5 and AssertJ
- **Default:** `language-default`
- **Why:** Teams choose differently.
- **Applies to:** implementer, test writer
- **Source:** own
"""


def area_file(*rules, title="# CORE-TEST · Tests"):
    return title + "\n\nOpening prose.\n\n" + "\n".join(rules)


class RulebookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def assertFails(self, name, text, message):
        path = self.write(name, text)
        with self.assertRaises(rulebook.RulebookError) as caught:
            rulebook.read_rule_file(path)
        self.assertIn(message, str(caught.exception))

    def test_reads_the_real_principles_layer(self):
        layer = rulebook.read_layer(ROOT / "v2" / "rules" / "core")
        self.assertGreater(len(layer.rules), 30)
        retired = [rule for rule in layer.rules.values() if rule.status == "retired"]
        self.assertTrue(retired)
        self.assertTrue(all(Path(rule.file).name == "retired.md" for rule in retired))

    def test_parts_keep_line_breaks_and_nested_lists(self):
        (rule,) = rulebook.read_rule_file(self.write("test.md", area_file(RULE)))
        self.assertEqual(rule.id, "CORE-TEST-03")
        self.assertEqual(rule.area, "TEST")
        self.assertEqual(rule.kind, "principle")
        self.assertEqual(rule.applies_to, ["implementer", "test writer"])
        self.assertEqual(rule.text("Rule"), "Name each test after the situation it sets up\nand the result it expects.")
        self.assertEqual(rule.parts["Source"], ["", "- own (doc 03 example)", "- `a/b@1234567 c.md` (MIT)"])
        self.assertIsNone(rule.changes)

    def test_code_block_may_hold_blank_lines(self):
        text = RULE.replace("- **Bad:** `testOrder2`", "- **Bad:**\n  ```java\n  void testOrder2() {}\n\n  ```")
        (rule,) = rulebook.read_rule_file(self.write("test.md", area_file(text)))
        self.assertEqual(rule.parts["Bad"], ["", "```java", "void testOrder2() {}", "", "```"])

    def test_unclosed_code_block_fails(self):
        text = RULE.replace("- **Bad:** `testOrder2`", "- **Bad:**\n  ```java\n  void testOrder2() {}")
        self.assertFails("test.md", area_file(text), "never closed")

    def test_decision_point(self):
        (point,) = rulebook.read_rule_file(self.write("test.md", area_file(DECISION_POINT, title="# CORE · DP")))
        self.assertTrue(point.is_decision_point)
        self.assertEqual(point.kind, "decision point")
        self.assertEqual(point.area, "DP")
        self.assertEqual(len(point.parts["Options"]), 3)

    def test_decision_point_with_a_kind_fails(self):
        text = DECISION_POINT.replace("- **Status:**", "- **Kind:** choice\n- **Status:**")
        self.assertFails("test.md", area_file(text, title="# CORE · DP"), "has a Kind")

    def test_missing_part_is_named(self):
        self.assertFails("test.md", area_file(RULE.replace("- **Review by:** 2027-11-03\n", "")), "missing Review by")

    def test_unknown_part_fails(self):
        self.assertFails("test.md", area_file(RULE.replace("- **Why:**", "- **Reason:**")), "unknown part")

    def test_part_twice_fails(self):
        self.assertFails("test.md", area_file(RULE + "- **Why:** again\n"), "appears twice")

    def test_unknown_line_shape_fails(self):
        self.assertFails("test.md", area_file(RULE + "\nA closing remark.\n"), "no known shape")

    def test_heading_in_opening_prose_fails(self):
        self.assertFails("test.md", "# CORE-TEST · Tests\n\n### Not a rule\n\n" + RULE, "outside a rule")

    def test_unknown_kind_and_status_fail(self):
        self.assertFails("a.md", area_file(RULE.replace("principle", "guideline")), "unknown Kind")
        self.assertFails("b.md", area_file(RULE.replace("active", "draft")), "unknown Status")

    def test_bad_id_and_wrong_file_fail(self):
        self.assertFails("a.md", area_file(RULE.replace("CORE-TEST-03", "CORE-TEST-3")), "not a rule")
        self.assertFails("b.md", area_file(RULE, title="# CORE-NAME · Names"), "does not belong")

    def test_retired_rules_live_only_in_retired_files(self):
        retired = RULE.replace("- **Status:** active",
                               "- **Status:** retired\n- **Replaced by:** CORE-TEST-04, CORE-TEST-05")
        self.assertFails("test.md", area_file(retired), "retired rules live in retired files")
        self.assertFails("retired.md", area_file(RULE, title="# Retired rules · Principles layer"), "only there")
        (rule,) = rulebook.read_rule_file(self.write("retired-test.md",
                                                     area_file(retired, title="# Retired rules · Principles layer")))
        self.assertEqual(rule.replaced_by, ["CORE-TEST-04", "CORE-TEST-05"])

    def test_retired_without_replaced_by_fails(self):
        retired = RULE.replace("- **Status:** active", "- **Status:** retired")
        self.assertFails("retired.md", area_file(retired, title="# Retired rules · Principles layer"), "Replaced by")

    def test_one_change_relation_only(self):
        overrides = RULE.replace("CORE-TEST-03", "APP-TEST-01").replace(
            "- **Kind:**", "- **Overrides:** CORE-TEST-03\n- **Kind:**")
        (rule,) = rulebook.read_rule_file(self.write("a.md", area_file(overrides, title="# APP-TEST · Tests")))
        self.assertEqual(rule.changes, ("Overrides", "CORE-TEST-03"))
        both = overrides.replace("- **Kind:**", "- **Tightens:** CORE-TEST-04\n- **Kind:**")
        self.assertFails("b.md", area_file(both, title="# APP-TEST · Tests"), "more than one")

    def test_file_must_end_with_newline(self):
        self.assertFails("test.md", area_file(RULE).rstrip("\n"), "newline")

    def test_layer_skips_index_and_rejects_duplicate_ids(self):
        self.write("index.md", "anything at all\n")
        self.write("a.md", area_file(RULE))
        self.assertEqual(list(rulebook.read_layer(self.dir).rules), ["CORE-TEST-03"])
        self.write("b.md", area_file(RULE))
        with self.assertRaises(rulebook.RulebookError) as caught:
            rulebook.read_layer(self.dir)
        self.assertIn("already defined", str(caught.exception))


ROLES = """# Roles

## Roles

| Role | Group | Purpose | Produces | Never does | Model class | Independent |
|---|---|---|---|---|---|---|
| implementer | delivery | Builds one story | The change | Judge its own work | standard | no |
| claims writer | delivery | Writes the claims | Claims | | standard | no |

## Jobs

| Job | Roles | Skills in order | `rest` skill |
|---|---|---|---|
"""


class RolesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "roles.md"

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, text):
        self.path.write_text(text, encoding="utf-8")
        return rulebook.read_roles(self.path)

    def test_reads_the_real_roles_file(self):
        roles = rulebook.read_roles(ROOT / "v2" / "roles.md")
        self.assertIn("skill judge", roles["roles"])
        self.assertIn("claims writer", roles["roles"])

    def test_empty_jobs_table_passes_and_rows_split(self):
        self.assertEqual(self.read(ROLES)["jobs"], {})
        jobs = self.read(ROLES + "| build | implementer | implementer, docs-writer | implementer |\n")["jobs"]
        self.assertEqual(jobs["build"]["Skills in order"], ["implementer", "docs-writer"])
        self.assertEqual(jobs["build"]["Roles"], ["implementer"])

    def test_wrong_header_and_reserved_name_fail(self):
        for text, message in ((ROLES.replace("| Purpose |", "| Aim |"), "header"),
                              (ROLES.replace("| claims writer |", "| every role |"), "reserved"),
                              (ROLES + "| build | implementer |\n", "cells")):
            with self.assertRaises(rulebook.RulebookError) as caught:
                self.read(text)
            self.assertIn(message, str(caught.exception))


class FrontmatterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "SKILL.tmpl.md"

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, front):
        self.path.write_text("---\n" + front + "---\n\n# Body\n", encoding="utf-8")
        return rulebook.read_frontmatter(self.path)

    def test_reads_strings_and_metadata(self):
        data, body = self.read('name: claims-writer\ndescription: "Writes claims."\nmetadata:\n'
                               "  roles: claims writer\n  areas: rest\n")
        self.assertEqual(data["description"], "Writes claims.")
        self.assertEqual(data["metadata"], {"roles": "claims writer", "areas": "rest"})
        self.assertEqual(body, 7)

    def test_other_shapes_fail(self):
        for front in ("allowed-tools: Bash\n", "metadata:\n  roles:\n    - a\n", "name: a\nname: b\n", "- item\n"):
            with self.assertRaises(rulebook.RulebookError):
                self.read(front)


if __name__ == "__main__":
    unittest.main()
