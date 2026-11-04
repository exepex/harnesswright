"""Tests for rulebook.py; each bad case asserts its own message. Run: python3 -m unittest discover -s v2/build/tests"""

import sys
import textwrap
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "v2" / "build"))

import rulebook  # noqa: E402

TITLE = "# CORE-TEST · Tests\n\nOpening prose.\n\n"
RETIRED_TITLE = "# Retired rules · Principles layer\n\n"
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
- **Tool:** `grep -n test`
- **Exceptions:** generated tests
- **Source:**
  - own (doc 03 example)
  - `a/b@1234567 c.md` (MIT)
"""
POINT = """### CORE-DP-TEST-STACK · Which test tools a language uses

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
RETIRED = RULE.replace("- **Status:** active", "- **Status:** retired\n- **Replaced by:** CORE-TEST-04, CORE-TEST-05")
APP = RULE.replace("CORE-TEST-03", "APP-TEST-01").replace("- **Kind:**", "- **Binds:** CORE-DP-TEST-STACK\n- **Kind:**")

# (file name, file text, the message its check must give)
BAD_FILES = [
    ("a.md", "# no title\n\n" + RULE, "first line is not the file title"),
    ("a.md", TITLE + "### Not a rule\n\n" + RULE, "outside a rule"),
    ("a.md", TITLE + "- **Kind:** floor\n\n" + RULE, "outside a rule"),
    ("a.md", TITLE + RULE + "\nA closing remark.\n", "no known shape"),
    ("a.md", TITLE + RULE.replace("- **Why:**", "- **Reason:**"), "not allowed in CORE-TEST-03"),
    ("a.md", TITLE + RULE.replace("- **Why:**", "- **Default:**"), "not allowed in CORE-TEST-03"),
    ("a.md", TITLE + RULE + "- **Why:** again\n", "appears twice"),
    ("a.md", TITLE + RULE + "\n" + RULE, "already defined in this file"),
    ("a.md", TITLE + RULE.replace("- **Review by:** 2027-11-03\n", ""), "missing Review by"),
    ("a.md", TITLE + RULE.replace("principle", "guideline"), "Kind has no allowed value"),
    ("a.md", TITLE + RULE.replace("- **Status:** active", "- **Status:** draft"), "Status has no allowed value"),
    ("a.md", TITLE + RULE.replace("2027-11-03", "20271103"), "Review by has no allowed value"),
    ("a.md", TITLE + RULE.replace(":** implementer, test writer", ":**"), "Applies to has no allowed value"),
    ("a.md", TITLE + RULE.replace("implementer, test writer", "Implementer"), "Applies to has no allowed value"),
    ("a.md", TITLE + RULE.replace(":** A failing test should say what broke.", ":**"), "Why has no allowed value"),
    ("a.md", TITLE + RULE.replace("  - own (doc 03 example)\n", "  text\n"), "Source has no allowed value"),
    ("a.md", TITLE + RULE.replace("CORE-TEST-03", "CORE-03"), "not a rule or decision point ID"),
    ("a.md", "# CORE-NAME · Names\n\n" + RULE, "does not belong in a file titled CORE-NAME"),
    ("a.md", "# CORE · Mixed\n\n" + RULE, "does not belong in a file titled CORE"),
    ("a.md", TITLE + POINT, "does not belong in a file titled CORE-TEST"),
    ("a.md", TITLE + RULE.replace("- **Status:** active", "- **Status:** active\n- **Replaced by:** CORE-TEST-04"),
     "exactly when the status is retired"),
    ("a.md", TITLE + RETIRED, "retired rules live in retired files"),
    ("retired.md", RETIRED_TITLE + RULE, "retired rules live in retired files"),
    ("retired.md", RETIRED_TITLE + RETIRED.replace("CORE-TEST-04, CORE-TEST-05", "the new one"),
     "Replaced by has no allowed value"),
    ("a.md", "# APP-TEST · T\n\n" + APP.replace("- **Kind:**", "- **Tightens:** CORE-TEST-03\n- **Kind:**"),
     "more than one"),
    ("a.md", "# APP-TEST · T\n\n" + APP.replace("CORE-DP-TEST-STACK", "the point"), "Binds has no allowed value"),
    ("a.md", "# CORE-DP · Points\n\n" + POINT.replace("- **Status:**", "- **Kind:** choice\n- **Status:**"),
     "not allowed in CORE-DP-TEST-STACK"),
    ("a.md", "# CORE-DP · Points\n\n" + POINT.replace("  - `junit`", "  - junit"), "Options has no allowed value"),
    ("a.md", TITLE + RULE.replace("- **Bad:** `testOrder2`", "- **Bad:**\n  ```java\n  void t() {}"),
     "before the next part"),
    ("a.md", TITLE + RULE + "  ```\n", "code block is never closed"),
    ("a.md", TITLE + textwrap.indent(RULE, "  "), "outside a rule is not prose"),
    ("a.md", TITLE + RULE + "  ### CORE-TEST-04 · Next\n", "rule heading must not be indented"),
    ("a.md", TITLE + RULE.replace("2027-11-03", "2027-13-45"), "Review by has no allowed value"),
    ("a.md", TITLE + RULE.replace("implementer, test writer", "implementer, implementer"), "Applies to has no"),
    ("a.md", TITLE + RULE.replace("  - own (doc", "    - own (doc"), "Source has no allowed value"),
    ("retired.md", RETIRED_TITLE + RETIRED.replace(" CORE-TEST-04, CORE-TEST-05", ""), "Replaced by has no allowed"),
    ("a.md", "# CORE-DP · Points\n\n" + POINT.replace("- **Options:**", "- **Options:** junit"), "Options has no"),
    ("a.md", (TITLE + RULE).rstrip("\n"), "does not end with a newline"),
    ("a.md", (TITLE + RULE).replace("\n", "\r\n"), "carriage return"),
]


class TempTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)


class RuleFileTest(TempTest):
    def read(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8", newline="")
        return rulebook.read_rule_file(path)

    def test_each_bad_file_fails_with_its_message(self):
        for name, text, message in BAD_FILES:
            with self.subTest(message=message):
                with self.assertRaises(rulebook.RulebookError) as caught:
                    self.read(name, text)
                self.assertIn(message, str(caught.exception))

    def test_reads_the_real_principles_layer(self):
        layer = rulebook.read_layer(ROOT / "v2" / "rules" / "core")
        self.assertGreater(len(layer.rules), 30)
        retired = [rule for rule in layer.rules.values() if rule.status == "retired"]
        self.assertTrue(retired and all(Path(rule.file).name == "retired.md" for rule in retired))

    def test_parts_keep_line_breaks_and_nested_lists(self):
        (rule,) = self.read("a.md", TITLE + RULE)
        self.assertEqual((rule.id, rule.text("Kind")), ("CORE-TEST-03", "principle"))
        self.assertEqual(rule.text("Rule"), "Name each test after the situation it sets up\nand the result it expects.")
        self.assertEqual(rule.parts["Source"], ["", "- own (doc 03 example)", "- `a/b@1234567 c.md` (MIT)"])
        self.assertEqual((rule.text("Tool"), rule.text("Exceptions")), ("`grep -n test`", "generated tests"))

    def test_code_block_may_hold_blank_lines_and_shorter_fences(self):
        block = "\n  ````md\n  ```py\n  ````py\n\n  ### X · Y\n  ```\n\n  ````"
        text = RULE.replace("- **Bad:** `testOrder2`", "- **Bad:**" + block)
        (rule,) = self.read("a.md", TITLE + text)
        self.assertEqual(rule.parts["Bad"], ["", "````md", "```py", "````py", "", "### X · Y", "```", "", "````"])

    def test_decision_point_retired_rule_and_binding(self):
        (point,) = self.read("a.md", "# CORE-DP · Points\n\n" + POINT.replace("TEST-STACK", "HTTP-02"))
        self.assertTrue(point.is_decision_point)
        (rule,) = self.read("retired-test.md", RETIRED_TITLE + RETIRED)
        self.assertEqual(rule.text("Replaced by"), "CORE-TEST-04, CORE-TEST-05")
        self.read("retired.md", RETIRED_TITLE + RETIRED.replace("CORE-TEST-04, CORE-TEST-05", "no replacement"))
        (app,) = self.read("b.md", "# APP-TEST · Tests\n\n" + APP)
        self.assertEqual(app.text("Binds"), "CORE-DP-TEST-STACK")

    def test_layer_reads_rule_files_only_and_rejects_duplicates(self):
        for name in ("index.md", "README.md"):
            (self.dir / name).write_text("anything at all\n", encoding="utf-8")
        self.read("a.md", TITLE + RULE)
        self.assertEqual(list(rulebook.read_layer(self.dir).rules), ["CORE-TEST-03"])
        self.read("b.md", TITLE + RULE)
        for folder, message in ((self.dir, "already defined"), (self.dir / "missing", "not a layer folder"),
                                (self.dir / "a.md", "not a layer folder")):
            with self.subTest(message=message):
                with self.assertRaises(rulebook.RulebookError) as caught:
                    rulebook.read_layer(folder)
                self.assertIn(message, str(caught.exception))


ROLES = """# Roles

## Roles

| Role | Group | Purpose | Produces | Never does | Model class | Independent |
|---|---|---|---|---|---|---|
| implementer | delivery | Builds one story | The change | Judge its own work | standard | no |
| claims writer | delivery | Writes the claims | Claims | | standard or deep | no |

## Jobs

Prose before the table.

| Job | Roles | Skills in order | `rest` skill |
|---|---|---|---|
"""
JOB = "| build | implementer | implementer, docs-writer | implementer |\n"
BAD_ROLES = [
    (ROLES.replace("## Jobs", "## Jobs\n\n## Jobs"), "exactly one '## Jobs'"),
    (ROLES.replace("| Purpose |", "| Aim |"), "expected one table"),
    (ROLES.replace("|---|---|---|---|---|---|---|", "|---|"), "not a header, a rule line and rows"),
    (ROLES.replace("Judge its own work | standard | no |", "Judge its own work | standard | no"), "cells"),
    (ROLES.replace("| claims writer |", "\n| claims writer |"), "only blank lines may follow"),
    (ROLES.replace("| claims writer |", "| implementer |"), "listed twice"),
    (ROLES.replace("| claims writer |", "| every role |"), "no allowed value"),
    (ROLES.replace("Writes the claims", ""), "no allowed value"),
    (ROLES.replace("standard or deep", "huge"), "no allowed value"),
    (ROLES.replace("| standard | no |", "| standard | maybe |"), "no allowed value"),
    (ROLES + JOB + JOB, "listed twice"),
    (ROLES + JOB.replace("| implementer | implementer,", "| every role | implementer,"), "no allowed value"),
    (ROLES + JOB.replace("| implementer |\n", "| other |\n"), "no allowed value"),
    (ROLES + JOB.replace("implementer, docs-writer", ""), "no allowed value"),
    (ROLES + JOB.replace("docs-writer", "Docs"), "no allowed value"),
    (ROLES.replace("| delivery | Builds", "| Delivery | Builds"), "no allowed value"),
    (ROLES.replace("Prose before the table.", "| stray |"), "not a header, a rule line and rows"),
    (ROLES[:-len("|---|---|---|---|\n")], "not a header, a rule line and rows"),
]


class RolesTest(TempTest):
    def read(self, text):
        (self.dir / "roles.md").write_text(text, encoding="utf-8")
        return rulebook.read_roles(self.dir / "roles.md")

    def test_reads_the_real_roles_file(self):
        roles = rulebook.read_roles(ROOT / "v2" / "roles.md")
        self.assertIn("skill judge", roles["roles"])

    def test_empty_jobs_table_passes_and_rows_split(self):
        self.assertEqual(self.read(ROLES)["jobs"], {})
        job = self.read(ROLES + JOB)["jobs"]["build"]
        self.assertEqual((job["Roles"], job["Skills in order"]), (["implementer"], ["implementer", "docs-writer"]))

    def test_each_bad_roles_file_fails_with_its_message(self):
        for text, message in BAD_ROLES:
            with self.subTest(text=text[-120:]):
                with self.assertRaises(rulebook.RulebookError) as caught:
                    self.read(text)
                self.assertIn(message, str(caught.exception))


class FrontmatterTest(TempTest):
    def read(self, front, body="---\n\n# Body\n"):
        (self.dir / "SKILL.tmpl.md").write_text("---\n" + front + body, encoding="utf-8")
        return rulebook.read_frontmatter(self.dir / "SKILL.tmpl.md")

    def test_reads_strings_and_metadata(self):
        data, body = self.read("name: claims-writer\ndescription: \"Use when: a story is done.\"\nmetadata:\n"
                               "  roles: claims writer\n  areas: rest\nlicense: 'Apache-2.0'\n")
        self.assertEqual(data["description"], "Use when: a story is done.")
        self.assertEqual(data["metadata"], {"roles": "claims writer", "areas": "rest"})
        self.assertEqual((data["license"], body), ("Apache-2.0", 8))

    def test_each_bad_frontmatter_fails_with_its_message(self):
        cases = [("name: a\n", "# Body\n", "frontmatter block"),
                 ("allowed-tools: Bash\n", "---\n", "no allowed shape"),
                 ("metadata: x\n", "---\n", "no allowed shape"),
                 ("metadata:\n  a: b\nmetadata:\n", "---\n", "no allowed shape"),
                 ("metadata:\n  roles:\n    - a\n", "---\n", "no allowed shape"),
                 ("metadata:\n  a: b\n  a: c\n", "---\n", "appears twice"),
                 ("name: a\nname: b\n", "---\n", "appears twice"),
                 ("name: a # note\n", "---\n", "quote it"),
                 ("description: Use when: x\n", "---\n", "quote it"),
                 ("description: 'it''s'\n", "---\n", "quote it"),
                 ('description: "say \\"hi\\""\n', "---\n", "quote it"),
                 ("name: a:\tb\n", "---\n", "quote it"),
                 ("name: a\t# c\n", "---\n", "quote it")]
        words = "y Y yes Yes YES n N no No NO true True TRUE false False FALSE on On ON off Off OFF null Null NULL"
        words += " ~ 2024 1.10 +.inf abc: a\tb a\x85b a\u2028b"
        for value in words.split(" "):
            cases.append((f"metadata:\n  v: {value}\n", "---\n", "quote it"))
        for front, body, message in cases:
            with self.subTest(front=front):
                with self.assertRaises(rulebook.RulebookError) as caught:
                    self.read(front, body)
                self.assertIn(message, str(caught.exception))

