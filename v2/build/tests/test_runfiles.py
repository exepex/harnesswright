"""Tests for runfiles.py part e2: one rules text per release skill, with one section per stack.
Run: python3 -m unittest discover -s v2/build/tests

Each test starts from test_resolve_layers' valid application and adds a release skill `implement`, the `rest` skill of
a job `implement` for the implementer, that copied every active CORE rule. So its rules text holds the rules of layers
2 to 6 in full, and one line for each change to a copied CORE rule.
"""

import hashlib
import io
import json
import unittest
from contextlib import redirect_stderr

from test_resolve_layers import TODAY, Application, area, rule  # puts v2/build on sys.path

import check_release  # noqa: E402
import reach  # noqa: E402
import repoprofile  # noqa: E402
import resolve  # noqa: E402
import rulebook  # noqa: E402

RELEASE = ".agents/harnesswright"
TEXT = ".harness/runs/r1/rules-text-implement.md"
JOBS = "| Job | Roles | Skills in order | `rest` skill |\n|---|---|---|---|\n"


class RulesTextTest(Application):
    def setUp(self):
        super().setUp()
        roles = self.repo / RELEASE / "roles.md"
        text = roles.read_text(encoding="utf-8")
        self.assertEqual(text.count(JOBS), 1)
        roles.write_text(text.replace(JOBS, JOBS + "| implement | implementer | implement | implement |\n"),
                         encoding="utf-8")
        core = rulebook.read_layer(self.repo / RELEASE / "rules/core")
        self.copied = sorted(r.id for r in core.rules.values() if r.status == "active")
        self.manifest(copied=self.copied)

    def manifest(self, **change):
        entry = {"job": "implement", "rest": True, "roles": ["implementer"], "areas": [], "copied-ids": self.copied}
        entry.update({k.replace("copied", "copied-ids"): v for k, v in change.items()})
        data = {"rulebook-version": "0.1.0", "skills": {"implement": entry}}
        self.write(RELEASE + "/manifest.json", json.dumps(data) + "\n")

    def outputs(self):
        inputs = resolve.load(self.repo, TODAY)
        return resolve.run_files(self.repo, "r1", TODAY, inputs)

    def text(self):
        texts = self.outputs()[1]
        self.assertEqual([p.name for p in texts], ["rules-text-implement.md"])
        return next(iter(texts.values()))

    def main(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = resolve.main(["--repo", str(self.repo), "--run", "r1", "--date", TODAY.isoformat()])
        self.last_err = err.getvalue()
        return code, self.last_err

    def section(self, text, title):
        return text.split(f"### {title}\n\n")[1].split("\n\n### ")[0].split("\n\n<!-- read-back")[0]

    def test_a_rules_text_holds_what_reaches_the_run(self):
        text = self.text()
        self.assertTrue(text.startswith("# Rules text: implement\n\n- **Release:** 0.1.0\n\n## Stack: java\n"))
        self.assertEqual(self.section(text, "Changes to rules that reach this run").splitlines(), [
            "- CORE-WORK-01 · Report only what you verified: tightened by COMP-ACME-WORK-01",
            "- JAVA-TEST-01 · Title of JAVA-TEST-01: replaced by APP-TEST-01",
            "- COMP-ACME-CODE-01 · Title of COMP-ACME-CODE-01: replaced by profile decisions",
            "- COMP-ACME-ERR-01 · Title of COMP-ACME-ERR-01: waived until 2027-03-01: legacy endpoints keep the old "
            "error format"])
        self.assertEqual(self.section(text, "Decision points"),
                         "- JAVA-DP-BOILERPLATE · How boilerplate is written: `lombok` (from profile decisions)")
        self.assertEqual(self.ids(self.section(text, "Floors")), ["COMP-ACME-WORK-01"])
        others = self.section(text, "Other rules")
        self.assertEqual(self.ids(others), ["COMP-ACME-ERR-01", "TEAM-ACME-LOG-01", "APP-TEST-01"])
        self.assertIn("- **Bad (do not do this):** not done\n- **Reason for the override:** Because.\n"
                      "<!-- end APP-TEST-01 -->", others)  # the expired waiver of TEAM-ACME-LOG-01 leaves no line
        self.assertTrue(text.endswith("<!-- read-back -->\nRules in this text: 4. Last rule: APP-TEST-01 · "
                                      "Title of APP-TEST-01.\n<!-- end read-back -->\n"))
        for loser in ("#### JAVA-TEST-01", "#### COMP-ACME-CODE-01", "#### CORE-"):  # never in full
            self.assertNotIn(loser, text)

    def ids(self, section):
        return [line.split()[2] for line in section.splitlines() if line.startswith("<!-- rule ")]

    def test_a_core_rule_the_skill_did_not_copy_is_written_in_full(self):
        self.manifest(copied=[])
        floors = self.section(self.text(), "Floors")
        self.assertEqual(self.ids(floors)[-1], "COMP-ACME-WORK-01")
        self.assertIn("CORE-WORK-01", self.ids(floors))
        self.assertIn("- **Tightened by:** COMP-ACME-WORK-01\n<!-- end CORE-WORK-01 -->", floors)

    def test_a_two_step_override_chain_leaves_one_line_per_loser(self):
        self.write("../acme/company/t.md", area("COMP-ACME-T", rule(
            "COMP-ACME-T-01", "idiom", "- **Overrides:** JAVA-TEST-01\n")))
        self.edit(".harness/standards/test.md", "Overrides:** JAVA-TEST-01", "Overrides:** COMP-ACME-T-01")
        text = self.text()
        marks = self.section(text, "Changes to rules that reach this run")
        self.assertIn("- JAVA-TEST-01 · Title of JAVA-TEST-01: replaced by COMP-ACME-T-01\n", marks)
        self.assertIn("- COMP-ACME-T-01 · Title of COMP-ACME-T-01: replaced by APP-TEST-01", marks)
        self.assertNotIn("#### COMP-ACME-T-01", text)
        self.assertIn("#### APP-TEST-01", text)

    def test_an_override_of_a_core_rule_follows_the_language_rule_in_its_place(self):
        self.write(".agents/harnesswright/rules/core/x.md", area("CORE-X", rule(
            "CORE-X-01", "principle", applies="test writer")))
        self.write(".agents/harnesswright/rules/java/x.md", area("JAVA-X", rule(
            "JAVA-X-01", "idiom", "- **Overrides:** CORE-X-01\n")))
        self.write(".harness/standards/x.md", area("APP-X", rule(
            "APP-X-01", "idiom", "- **Overrides:** CORE-X-01\n", "test writer")))
        text = self.text()
        self.assertIn("- JAVA-X-01 · Title of JAVA-X-01: replaced by APP-X-01", text)
        self.assertIn("#### APP-X-01", text)  # it replaces a rule that reaches, so it reaches
        self.assertNotIn("CORE-X-01", text)

    def test_a_rule_outside_the_skill_does_not_reach(self):
        self.manifest(rest=False, areas=[])
        text = self.text()
        self.assertNotIn("TEAM-ACME-LOG-01", text)  # a choice of an area the skill does not list
        self.assertIn("#### COMP-ACME-WORK-01", text)  # a floor of every role reaches every run
        self.assertIn("- JAVA-DP-BOILERPLATE · ", text)  # a decision point of the run's role reaches

    def test_each_stack_has_its_own_section_and_read_back(self):
        self.edit(".harness/profile.yaml", "[java]", "[java, kotlin]")
        self.write(".agents/harnesswright/rules/kotlin/k.md", area("KOTLIN-K", rule("KOTLIN-K-01")))
        text = self.text()
        java, kotlin = text.split("## Stack: java\n")[1].split("## Stack: kotlin\n")
        self.assertEqual(text.count("<!-- read-back -->"), 2)
        self.assertIn("Last rule: APP-TEST-01 · ", java)
        self.assertIn("#### KOTLIN-K-01", kotlin)
        for other in ("JAVA-", "APP-TEST-01", "COMP-ACME-CODE-01"):
            self.assertNotIn(other, kotlin)
        self.assertIn("Rules in this text: 4. Last rule: TEAM-ACME-LOG-01 · ", kotlin)

    def test_rules_md_records_each_rules_text_hash(self):
        self.assertEqual(self.main()[0], 0)
        text = (self.repo / TEXT).read_bytes()
        rules_md = (self.repo / ".harness/runs/r1/rules.md").read_text(encoding="utf-8")
        self.assertIn(f"## Rules texts\n\n| SHA-256 | File |\n|---|---|\n| {hashlib.sha256(text).hexdigest()} | "
                      f"{TEXT} |\n\n## Parked skills\n\n| Skill | Size | Limit | Owner of the largest layer |\n"
                      "|---|---|---|---|\n", rules_md)
        self.assertTrue(rules_md.endswith("|---|---|---|---|\n"))
        self.assertIn("and 1 rules texts", self.last_err)
        self.assertEqual(self.main()[0], 0)  # a second resolve of the same run writes the same bytes

    def test_a_rules_text_over_the_limit_parks_the_skill(self):
        self.write("../acme/team/big.md", area("TEAM-ACME-BIG", rule("TEAM-ACME-BIG-01").replace(
            "Do it.", "Do it. " + "x" * 900)))
        self.edit(".harness/profile.yaml", "rules-text-limit: 45000", "rules-text-limit: 1000")
        code, err = self.main()
        self.assertEqual(code, 3)
        self.assertFalse((self.repo / TEXT).exists())
        rules_md = (self.repo / ".harness/runs/r1/rules.md").read_text(encoding="utf-8")
        self.assertRegex(rules_md, r"\| implement \| [0-9]+ \| 1000 \| Acme payments team \|\n$")
        self.assertIn("## Rules texts\n\n| SHA-256 | File |\n|---|---|\n\n", rules_md)
        self.assertIn("resolve: parked implement: its rules text is ", err)
        self.assertIn("it goes to Acme payments team. Sizes per layer and area:\n", err)
        self.assertIn("  TEAM-ACME BIG: ", err)

    def test_a_manifest_resolve_cannot_place_stops(self):
        for change, expected in (({"rest": "yes"}, "cannot be read as a release manifest"),
                                 ({"job": "ship"}, "names skills of jobs roles.md does not list: ['implement']"),
                                 ({"copied": ["CORE-WORK-99"]}, "cited CORE-WORK-99 is not in the rulebook")):
            with self.subTest(expected=expected):
                self.manifest(**change)
                code, err = self.main()
                self.assertEqual(code, 1)
                self.assertIn(expected, err)
                self.assertFalse((self.repo / ".harness/runs/r1").exists())

    def test_the_ceiling_is_the_release_check_s(self):
        self.assertEqual(reach.CEILING, check_release.CEILING)
        self.assertEqual(reach.CEILING, repoprofile.DEFAULT_LIMIT)


if __name__ == "__main__":
    unittest.main()
