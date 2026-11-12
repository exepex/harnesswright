"""Tests for resolve.py part e1b: combining the layers (doc 03 steps 1 to 4) and writing rules.md.
Run: python3 -m unittest discover -s v2/build/tests

Each test starts from test_resolve_layers' valid application: JAVA-TEST-01 is overridden by APP-TEST-01, CORE-WORK-01
is tightened by COMP-ACME-WORK-01, COMP-ACME-CODE-01 binds JAVA-DP-BOILERPLATE to records, and the profile binds it
to lombok, waives COMP-ACME-ERR-01 and holds an expired waiver of TEAM-ACME-LOG-01.
"""

import hashlib
import io
import unittest
from contextlib import redirect_stderr

from test_resolve_layers import POINT, TODAY, Application, area, rule  # puts v2/build on sys.path

import resolve  # noqa: E402

BINDING = "- **Binds:** JAVA-DP-BOILERPLATE: records\n"
DECISION = "decisions:\n  boilerplate: lombok\n"


class RulesTest(Application):
    def load(self):
        return resolve.combine(resolve.load(self.repo, TODAY))

    def text(self):
        inputs = resolve.load(self.repo, TODAY)
        return resolve.rules_md(self.repo, "r1", TODAY, inputs, resolve.combine(inputs))

    def main(self, run="r1"):
        err = io.StringIO()
        with redirect_stderr(err):
            code = resolve.main(["--repo", str(self.repo), "--run", run, "--date", TODAY.isoformat()])
        return code, err.getvalue()

    def test_rules_md_lists_what_applies_in_layer_order(self):
        text = self.text()
        rows = [
            "| CORE-WORK-01 | CORE | floor |  |  |",
            "| JAVA-DP-BOILERPLATE | JAVA | decision point |  |  |",
            "| COMP-ACME-ERR-01 | COMP-ACME | choice |  | waived until 2027-03-01 |",
            "| COMP-ACME-WORK-01 | COMP-ACME | floor | Tightens CORE-WORK-01 |  |",
            "| TEAM-ACME-LOG-01 | TEAM-ACME | choice |  |  |",
            "| APP-TEST-01 | APP | idiom | Overrides JAVA-TEST-01 |  |",
        ]
        for line in rows:
            self.assertIn(line + "\n", text)
        self.assertEqual([text.index(line) for line in rows], sorted(text.index(line) for line in rows))
        self.assertNotIn("| JAVA-TEST-01 | JAVA |", text)
        self.assertNotIn("| COMP-ACME-CODE-01 | COMP-ACME |", text)  # its binding lost to the profile's
        self.assertIn("| JAVA-TEST-01 | APP-TEST-01 |\n| COMP-ACME-CODE-01 | profile decisions |\n", text)
        self.assertIn("| JAVA-DP-BOILERPLATE | lombok | profile decisions |\n", text)
        self.assertIn("| COMP-ACME-ERR-01 | legacy endpoints keep the old error format | 2027-03-01 | "
                      "app-owner, acme-owner | applied |\n", text)
        self.assertIn("| TEAM-ACME-LOG-01 | old logger | 2026-01-01 | app-owner | expired |\n", text)
        profile = hashlib.sha256((self.repo / ".harness/profile.yaml").read_bytes()).hexdigest()
        self.assertIn(f"| {profile} | .harness/profile.yaml |\n", text)
        self.assertIn(" | ../acme/company/layer.yaml |\n", text)
        self.assertIn(" | .agents/harnesswright/rules/java/dp.md |\n", text)
        self.assertNotIn("Do it.", text)  # no rule text

    def test_a_point_takes_the_most_specific_binding_then_its_default(self):
        self.edit(".harness/profile.yaml", DECISION, "")
        text = self.text()
        self.assertIn("| JAVA-DP-BOILERPLATE | records | COMP-ACME-CODE-01 |\n", text)
        self.assertIn("| COMP-ACME-CODE-01 | COMP-ACME | choice | Binds JAVA-DP-BOILERPLATE: records |  |\n", text)
        self.edit("../acme/company/code.md", BINDING, "")
        self.assertIn("| JAVA-DP-BOILERPLATE | records | default |\n", self.text())
        self.setUp()
        self.edit(".harness/profile.yaml", DECISION, "")
        self.write(".harness/standards/code.md", area("APP-CODE", rule(
            "APP-CODE-01", extra="- **Overrides:** COMP-ACME-CODE-01\n")))
        self.assertStops("APP-CODE-01: Overrides COMP-ACME-CODE-01, a binding; a binding changes only by binding")
        self.setUp()
        point = ".agents/harnesswright/rules/java/dp.md"
        for default in ("none", "`records` or `lombok`", "`getters`", "`records`, not `lombok`"):
            with self.subTest(default=default):
                self.edit(point, "- **Default:** `records`", f"- **Default:** {default}")
                self.assertStops("JAVA-DP-BOILERPLATE: Default must name exactly one of its Options in backticks")
                self.edit(point, f"- **Default:** {default}", "- **Default:** `records`")

    def test_a_point_bound_twice_in_one_layer_stops(self):
        self.write("../acme/company/more.md", area("COMP-ACME-MORE", rule(
            "COMP-ACME-MORE-01", extra="- **Binds:** JAVA-DP-BOILERPLATE: lombok\n")))
        self.assertStops("binds JAVA-DP-BOILERPLATE, which COMP-ACME-CODE-01 already binds in layer COMP-ACME")
        self.setUp()
        self.write(".harness/standards/code.md", area("APP-CODE", rule(
            "APP-CODE-01", extra="- **Binds:** JAVA-DP-BOILERPLATE: records\n")))
        self.assertStops("profile.yaml:30: JAVA-DP-BOILERPLATE is bound twice in the application layer: here and "
                         "by APP-CODE-01")
        self.edit(".harness/profile.yaml", DECISION, "")
        self.assertIn("| JAVA-DP-BOILERPLATE | records | APP-CODE-01 |\n", self.text())

    def test_a_change_names_a_rule_that_still_applies(self):
        self.write("../acme/company/test.md", area("COMP-ACME-TEST", rule(
            "COMP-ACME-TEST-01", "idiom", "- **Overrides:** JAVA-TEST-01\n")))
        self.assertStops("test.md:3: APP-TEST-01 Overrides JAVA-TEST-01, which COMP-ACME-TEST-01 already replaces; "
                         "name that rule instead")
        self.write("../acme/company/more.md", area("COMP-ACME-MORE", rule(
            "COMP-ACME-MORE-01", "idiom", "- **Overrides:** JAVA-TEST-01\n")))
        self.assertStops("COMP-ACME-MORE-01 already replaces; its layer's owner keeps one of the two")
        (self.repo / "../acme/company/more.md").unlink()
        self.edit(".harness/standards/test.md", "Overrides:** JAVA-TEST-01", "Overrides:** COMP-ACME-TEST-01")
        self.edit(".harness/profile.yaml", "TEAM-ACME-LOG-01\n    reason: old logger\n    until: 2026-01-01",
                  "JAVA-TEST-01\n    reason: old logger\n    until: 2027-01-01")
        text = self.text()
        self.assertIn("| JAVA-TEST-01 | COMP-ACME-TEST-01 |\n| COMP-ACME-TEST-01 | APP-TEST-01 |\n", text)
        self.assertIn("| JAVA-TEST-01 | old logger | 2027-01-01 | app-owner | replaced by APP-TEST-01 |\n", text)
        self.assertNotIn("| COMP-ACME-TEST-01 | COMP-ACME |", text)

    def test_a_language_default_is_bound_again(self):
        stack = POINT.replace("JAVA-DP-BOILERPLATE", "CORE-DP-STACK").replace("`records`", "`junit`").replace(
            "`lombok`", "`testng`")
        self.write(".agents/harnesswright/rules/core/dp.md", area("CORE-DP", stack))
        self.write(".agents/harnesswright/rules/java/stack.md", area("JAVA-STACK", rule(
            "JAVA-STACK-01", extra="- **Binds:** CORE-DP-STACK: testng\n")))
        self.assertIn("| CORE-DP-STACK | testng | JAVA-STACK-01 |\n", self.text())
        self.write("../acme/company/stack.md", area("COMP-ACME-STACK", rule(
            "COMP-ACME-STACK-01", extra="- **Binds:** CORE-DP-STACK: junit\n")))
        text = self.text()
        self.assertIn("| CORE-DP-STACK | junit | COMP-ACME-STACK-01 |\n", text)
        self.assertIn("| JAVA-STACK-01 | COMP-ACME-STACK-01 |\n", text)
        self.edit(".harness/profile.yaml", DECISION, DECISION + "  stack: testng\n")
        text = self.text()
        self.assertIn("| CORE-DP-STACK | testng | profile decisions |\n", text)
        self.assertIn("| JAVA-STACK-01 | COMP-ACME-STACK-01 |\n", text)
        self.assertIn("| COMP-ACME-STACK-01 | profile decisions |\n", text)
        self.assertNotIn("| JAVA-STACK-01 | JAVA |", text)
        self.edit(".harness/profile.yaml", "[java]", "[java, kotlin]")
        self.write(".agents/harnesswright/rules/kotlin/stack.md", area("KOTLIN-STACK", rule(
            "KOTLIN-STACK-01", extra="- **Binds:** CORE-DP-STACK: junit\n")))
        self.assertStops("KOTLIN-STACK-01 binds CORE-DP-STACK, which JAVA-STACK-01 of another language binds")
        self.write(".agents/harnesswright/rules/kotlin/stack.md", area("KOTLIN-STACK", rule(
            "KOTLIN-STACK-01", "idiom", "- **Overrides:** JAVA-TEST-01\n")))
        self.assertStops("KOTLIN-STACK-01: Overrides JAVA-TEST-01, a rule of another language")

    def test_only_the_application_layer_counts_with_the_profile(self):
        self.edit(".harness/profile.yaml", "  repository: .harness/standards/\n", "")
        self.write("../acme/team/bind.md", area("TEAM-ACME-BIND", rule("TEAM-ACME-BIND-01", extra=BINDING)))
        text = self.text()
        self.assertIn("| JAVA-DP-BOILERPLATE | lombok | profile decisions |\n", text)
        self.assertIn("| COMP-ACME-CODE-01 | TEAM-ACME-BIND-01 |\n| TEAM-ACME-BIND-01 | profile decisions |\n", text)

    def test_waivers_show_their_status(self):
        self.edit(".harness/profile.yaml", "TEAM-ACME-LOG-01\n    reason: old logger\n    until: 2026-01-01",
                  "JAVA-TEST-01\n    reason: old | new\n    until: 2027-01-01")
        self.assertIn("| JAVA-TEST-01 | old \\| new | 2027-01-01 | app-owner | replaced by APP-TEST-01 |\n",
                      self.text())

    def test_rules_md_is_written_once_per_run(self):
        self.assertEqual(self.main()[0], 2)
        path = self.repo / ".harness/runs/r1/rules.md"
        written = path.read_bytes()
        self.assertEqual(written, self.text().encode("utf-8"))
        self.assertEqual(self.main(), (2, self.main()[1]))
        self.assertEqual(path.read_bytes(), written)
        self.edit("../acme/team/log.md", "Title of TEAM-ACME-LOG-01", "A new title")
        code, err = self.main()
        self.assertEqual((code, "already exists and differs from this resolve" in err), (1, True))
        self.assertEqual(path.read_bytes(), written)
        self.assertEqual(self.main("r2")[0], 2)
        self.assertNotEqual((self.repo / ".harness/runs/r2/rules.md").read_bytes(), written)
        code, err = self.main("../escape")
        self.assertEqual((code, "run id '../escape' must be" in err), (1, True))


if __name__ == "__main__":
    unittest.main()
