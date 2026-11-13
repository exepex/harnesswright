"""Tests for runfiles.py parts e2 and e3: one rules text per release skill and stack (one file per language).
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

from test_resolve_layers import POINT, TODAY, Application, area, rule  # puts v2/build on sys.path

import check_release  # noqa: E402
import reach  # noqa: E402
import repoprofile  # noqa: E402
import resolve  # noqa: E402
import rulebook  # noqa: E402

RELEASE = ".agents/harnesswright"
TEXT = ".harness/runs/r1/rules-text-implement.java.md"
JOBS = "| Job | Roles | Skills in order | `rest` skill |\n|---|---|---|---|\n"


class RulesTextTest(Application):
    def setUp(self):
        super().setUp()
        roles = self.repo / RELEASE / "roles.md"
        text = roles.read_text(encoding="utf-8")
        roles.write_text(text.replace(JOBS, JOBS + "| implement | implementer | implement | implement |\n"),
                         encoding="utf-8")
        core = rulebook.read_layer(self.repo / RELEASE / "rules/core")
        self.copied = sorted(r.id for r in core.rules.values() if r.status == "active")
        self.manifest(copied=self.copied)

    def manifest(self, skills=None, **change):
        entry = {"job": "implement", "rest": True, "roles": ["implementer"], "areas": [], "copied-ids": self.copied}
        entry.update({k.replace("copied", "copied-ids"): v for k, v in change.items()})
        data = {"rulebook-version": "0.1.0", "skills": skills or {"implement": entry}}
        self.write(RELEASE + "/manifest.json", json.dumps(data) + "\n")

    def jobs(self, row):
        roles = self.repo / RELEASE / "roles.md"
        text = roles.read_text(encoding="utf-8")
        old = JOBS + "| implement | implementer | implement | implement |\n"
        roles.write_text(text.replace(old, JOBS + row), encoding="utf-8")

    def outputs(self):
        inputs = resolve.load(self.repo, TODAY)
        return resolve.run_files(self.repo, "r1", TODAY, inputs)

    def text(self, stack="java"):
        texts = {p.name: text for p, text in self.outputs()[1].items()}
        return texts[f"rules-text-implement.{stack}.md"]

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
        self.assertLess(text.index("\n### Floors\n"), text.index("\n### Other rules\n"))
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
        self.assertTrue(text.endswith("<!-- read-back -->\nStack: java. Rules in this text: 4. Last rule: "
                                      "APP-TEST-01 · Title of APP-TEST-01.\n<!-- end read-back -->\n"))
        for loser in ("#### JAVA-TEST-01", "#### COMP-ACME-CODE-01", "#### CORE-"):  # never in full
            self.assertNotIn(loser, text)

    def ids(self, section):
        return [line.split()[2] for line in section.splitlines() if line.startswith("<!-- rule ")]

    def test_a_core_rule_the_skill_did_not_copy_is_written_in_full(self):
        self.manifest(copied=[])
        floors = self.section(self.text(), "Floors")
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

    def test_a_binding_that_replaces_a_reaching_binding_reaches(self):
        self.write(".agents/harnesswright/rules/core/dp.md", area("CORE-DP", POINT.replace(
            "JAVA-DP-BOILERPLATE", "CORE-DP-STYLE").replace("- **Applies to:** implementer", "- **Applies to:** "
                                                            "code reviewer")))
        self.write(".agents/harnesswright/rules/java/code.md", area("JAVA-CODE", rule(
            "JAVA-CODE-01", extra="- **Binds:** CORE-DP-STYLE: records\n")))
        self.write("../acme/company/sty.md", area("COMP-ACME-STY", rule(
            "COMP-ACME-STY-01", extra="- **Binds:** CORE-DP-STYLE: lombok\n", applies="code reviewer")))
        text = self.text()
        self.assertIn("- JAVA-CODE-01 · Title of JAVA-CODE-01: replaced by COMP-ACME-STY-01", text)
        self.assertIn("#### COMP-ACME-STY-01", text)

    def test_each_decision_point_line_names_where_its_option_came_from(self):
        self.edit(".harness/profile.yaml", "decisions:\n  boilerplate: lombok\n", "")
        self.assertIn("- JAVA-DP-BOILERPLATE · How boilerplate is written: `records` (from COMP-ACME-CODE-01)",
                      self.text())
        self.edit("../acme/company/code.md", "- **Binds:** JAVA-DP-BOILERPLATE: records\n", "")
        self.assertIn("- JAVA-DP-BOILERPLATE · How boilerplate is written: `records` (from default)", self.text())

    def test_a_rule_outside_the_skill_does_not_reach(self):
        self.manifest(rest=False, areas=[])
        text = self.text()
        self.assertNotIn("TEAM-ACME-LOG-01", text)  # a choice of an area the skill does not list
        self.assertIn("#### COMP-ACME-WORK-01", text)  # a floor of every role reaches every run
        self.assertIn("- JAVA-DP-BOILERPLATE · ", text)  # a decision point of the run's role reaches

    def test_each_stack_has_its_own_file_and_read_back(self):
        self.edit(".harness/profile.yaml", "[java]", "[java, kotlin]")
        self.write(".agents/harnesswright/rules/kotlin/k.md", area("KOTLIN-K", rule("KOTLIN-K-01")))
        self.assertEqual(sorted(p.name for p in self.outputs()[1]),
                         ["rules-text-implement.java.md", "rules-text-implement.kotlin.md"])
        java, kotlin = self.text("java"), self.text("kotlin")
        self.assertTrue(kotlin.startswith("# Rules text: implement\n\n- **Release:** 0.1.0\n\n## Stack: kotlin\n"))
        self.assertEqual((java.count("<!-- read-back -->"), java.count("## Stack: ")), (1, 1))
        self.assertIn("Last rule: APP-TEST-01 · ", java)
        self.assertIn("#### KOTLIN-K-01", kotlin)
        for other in ("JAVA-", "APP-TEST-01", "COMP-ACME-CODE-01"):
            self.assertNotIn(other, kotlin)
        self.assertIn("Stack: kotlin. Rules in this text: 4. Last rule: TEAM-ACME-LOG-01 · ", kotlin)
        big = rule("KOTLIN-BIG-01").replace("Do it.", "Do it. " + "x" * 2000)
        self.write(".agents/harnesswright/rules/kotlin/big.md", area("KOTLIN-BIG", big))
        limit = max(reach.size(java), reach.size(kotlin)) + 100
        self.edit(".harness/profile.yaml", "rules-text-limit: 45000", f"rules-text-limit: {limit}")
        code, err = self.main()  # each file has its own limit: only kotlin's, the second stack, is over it
        self.assertEqual(code, 3)
        self.assertTrue((self.repo / TEXT).exists())
        self.assertFalse((self.repo / ".harness/runs/r1/rules-text-implement.kotlin.md").exists())
        self.assertIn("resolve: parked implement (kotlin): ", err)
        rules_md = (self.repo / ".harness/runs/r1/rules.md").read_text(encoding="utf-8")
        self.assertIn("| implement | kotlin | ", rules_md)

    def test_rules_md_records_each_rules_text_hash(self):
        self.assertEqual(self.main()[0], 0)
        text = (self.repo / TEXT).read_bytes()
        rules_md = (self.repo / ".harness/runs/r1/rules.md").read_text(encoding="utf-8")
        self.assertIn(f"## Rules texts\n\n| SHA-256 | File |\n|---|---|\n| {hashlib.sha256(text).hexdigest()} | "
                      f"{TEXT} |\n\n## Parked rules texts\n\n"
                      "| Skill | Stack | Size | Limit | Owner of the largest layer |\n|---|---|---|---|---|\n",
                      rules_md)
        self.assertTrue(rules_md.endswith("|---|---|---|---|---|\n"))
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
        self.assertRegex(rules_md, r"\| implement \| java \| [0-9]+ \| 1000 \| Acme payments team \|\n$")
        self.assertIn("## Rules texts\n\n| SHA-256 | File |\n|---|---|\n\n", rules_md)
        self.assertIn("resolve: parked implement (java): its rules text is ", err)
        self.assertIn("it goes to Acme payments team. Sizes per layer and area:\n", err)
        self.assertIn("  TEAM-ACME BIG: ", err)

    def test_the_limit_holds_at_its_size_and_parks_one_over(self):
        size = reach.size(self.text())
        self.edit(".harness/profile.yaml", "rules-text-limit: 45000", f"rules-text-limit: {size}")
        self.assertEqual(self.main()[0], 0)
        self.setUp()
        self.edit(".harness/profile.yaml", "rules-text-limit: 45000", f"rules-text-limit: {size - 1}")
        self.assertEqual(self.main()[0], 3)

    def test_a_parked_skill_leaves_the_others_written(self):
        self.jobs("| implement | implementer | alpha, zeta | zeta |\n")
        alpha = {"job": "implement", "rest": False, "roles": ["implementer"], "areas": [], "copied-ids": self.copied}
        self.manifest({"zeta": dict(alpha, rest=True), "alpha": alpha})  # out of order on purpose
        big = rule("TEAM-ACME-BIG-01").replace("Do it.", "Do it. " + "x" * 900)
        self.write("../acme/team/big.md", area("TEAM-ACME-BIG", big, big.replace("BIG-01", "BIG-02")))
        self.edit(".harness/profile.yaml", "rules-text-limit: 45000", "rules-text-limit: 2000")
        code, err = self.main()
        self.assertEqual(code, 3)
        written = self.repo / ".harness/runs/r1/rules-text-alpha.java.md"
        self.assertFalse((self.repo / ".harness/runs/r1/rules-text-zeta.java.md").exists())
        rules_md = (self.repo / ".harness/runs/r1/rules.md").read_text(encoding="utf-8")
        self.assertIn(f"| {hashlib.sha256(written.read_bytes()).hexdigest()} | "
                      ".harness/runs/r1/rules-text-alpha.java.md |",
                      rules_md)
        self.assertRegex(rules_md, r"\| zeta \| java \| [0-9]+ \| 2000 \| Acme payments team \|\n$")
        big_size = int(err.split("  TEAM-ACME BIG: ")[1].split()[0])
        self.assertGreater(big_size, 2 * 900)  # both rules of the area count

    def test_a_manifest_resolve_cannot_place_stops(self):
        for change, expected in (({"rest": "yes"}, "cannot be read as a release manifest"),
                                 ({"job": "ship"}, "job implement lists skills ['implement'] in roles.md, but "),
                                 ({"copied": ["CORE-WORK-99"]}, "cited CORE-WORK-99 is not in the rulebook")):
            with self.subTest(expected=expected):
                self.manifest(**change)
                code, err = self.main()
                self.assertEqual(code, 1)
                self.assertIn(expected, err)
                self.assertFalse((self.repo / ".harness/runs/r1").exists())
        self.jobs("| implement | implementer | implement, ghost | implement |\n")
        self.manifest()
        self.assertIn("job implement lists skills ['implement', 'ghost'] in roles.md", self.main()[1])

    def test_the_ceiling_is_the_release_check_s(self):
        self.assertEqual(reach.CEILING, check_release.CEILING)
        self.assertEqual(reach.CEILING, repoprofile.DEFAULT_LIMIT)


if __name__ == "__main__":
    unittest.main()
