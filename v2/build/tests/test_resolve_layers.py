"""Tests for resolve.py part e1a: reading and checking the layers. Run: python3 -m unittest discover -s v2/build/tests

LayersTest starts from a valid application: the real release (CORE and roles.md), a java language layer with a
decision point, an acme company layer, an acme team layer and application rules, with test_resolve's profile. Each
test breaks one thing and asserts the message that names it.
"""

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import date
from pathlib import Path

from test_resolve import PROFILE, ROOT, resolve

TODAY = date(2026, 11, 12)


def rule(rule_id, kind="choice", extra="", applies="implementer"):
    return f"""### {rule_id} · Title of {rule_id}

- **Kind:** {kind}
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** {applies}
{extra}- **Rule:** Do it.
- **Why:** Because.
- **Check:** Is it done?
- **Good:** done
- **Bad:** not done
- **Eval:** a case that is not done
- **Source:** own
"""


POINT = """### JAVA-DP-BOILERPLATE · How boilerplate is written

- **Status:** active
- **Review by:** 2027-11-03
- **Question:** How is boilerplate written?
- **Options:**
  - `records`: the language's own records
  - `lombok`: Lombok
- **Default:** `records`
- **Why:** Teams choose differently.
- **Applies to:** implementer
- **Source:** own
"""


def area(prefix, *rules):
    return f"# {prefix} · Area\n\n" + "\n".join(rules)


class LayersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.tmp / "app"
        release = self.repo / ".agents/harnesswright"
        shutil.copytree(ROOT / "release", release)
        self.files = {
            ".agents/harnesswright/rules/java/dp.md": area("JAVA-DP", POINT),
            ".agents/harnesswright/rules/java/test.md": area("JAVA-TEST", rule("JAVA-TEST-01", "idiom")),
            "../acme/company/layer.yaml": "owner: Acme platform team\nversion: \"2.1.0\"\n",
            "../acme/company/err.md": area("COMP-ACME-ERR", rule("COMP-ACME-ERR-01")),
            "../acme/company/code.md": area("COMP-ACME-CODE", rule(
                "COMP-ACME-CODE-01", extra="- **Binds:** JAVA-DP-BOILERPLATE: records\n")),
            "../acme/company/work.md": area("COMP-ACME-WORK", rule(
                "COMP-ACME-WORK-01", "floor", "- **Tightens:** CORE-WORK-01\n", "every role")),
            "../acme/team/layer.yaml": "owner: Acme payments team\nversion: \"1.0.0\"\n",
            "../acme/team/log.md": area("TEAM-ACME-LOG", rule("TEAM-ACME-LOG-01")),
            ".harness/standards/test.md": area("APP-TEST", rule(
                "APP-TEST-01", "idiom", "- **Overrides:** JAVA-TEST-01\n")),
            ".harness/profile.yaml": PROFILE,
        }
        for rel, text in self.files.items():
            self.write(rel, text)

    def write(self, rel, text):
        path = (self.repo / rel).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def edit(self, rel, old, new):
        text = self.files[rel]
        self.assertEqual(text.count(old), 1, f"{old!r} must occur once in {rel}")
        self.files[rel] = text.replace(old, new)
        self.write(rel, self.files[rel])

    def load(self):
        return resolve.load(self.repo, TODAY)

    def assertStops(self, expected):
        with self.assertRaises(resolve.RulebookError) as caught:
            self.load()
        self.assertIn(expected, str(caught.exception))

    def test_a_valid_application_reads_every_layer_in_order(self):
        inputs = self.load()
        self.assertEqual([s.prefix for s in inputs.sources], ["CORE", "JAVA", "COMP-ACME", "TEAM-ACME", "APP"])
        self.assertEqual([s.owner for s in inputs.sources],
                         ["harnesswright", "harnesswright", "Acme platform team", "Acme payments team",
                          "the application owner"])
        self.assertEqual(inputs.decisions, {"JAVA-DP-BOILERPLATE": ("lombok", 30)})
        self.assertEqual([w["rule"] for w in inputs.waivers], ["COMP-ACME-ERR-01"])
        self.assertEqual([w["rule"] for w in inputs.expired], ["TEAM-ACME-LOG-01"])
        self.assertEqual(inputs.waivers[0]["approved by"], "app-owner, acme-owner")
        self.assertEqual(inputs.limit, 45000)
        names = [p.name for p in inputs.files]
        self.assertEqual(names[:3], ["profile.yaml", "manifest.json", "roles.md"])
        self.assertIn("layer.yaml", names)
        self.assertIn("work.md", names)

    def test_release_and_layer_versions_and_folders(self):
        cases = [
            (".harness/profile.yaml", '  version: "0.1.0"', '  version: "0.2.0"', "version 0.1.0 is not the profile's"),
            (".harness/profile.yaml", "  folder: .agents/harnesswright/", "  folder: elsewhere/",
             "manifest.json is missing"),
            (".harness/profile.yaml", "[java]", "[java, kotlin]", "language kotlin is not in the release"),
            (".harness/profile.yaml", "../acme/team/", "../acme/gone/", "layer acme: ../acme/gone/layer.yaml"),
            (".harness/profile.yaml", "  repository: .harness/standards/", "  repository: nowhere/",
             "layer application: folder"),
        ]
        for rel, old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit(rel, old, new)
                self.assertStops(expected.replace("../acme/gone/layer.yaml", ""))
        self.setUp()
        self.write(".agents/harnesswright/manifest.json", "not json\n")
        self.assertStops("manifest.json is missing or cannot be read")

    def test_layer_prefixes_and_order(self):
        cases = [
            ("../acme/team/log.md", "TEAM-ACME-LOG", "TEAM-OTHER-LOG", "must all carry one of COMP-ACME"),
            ("../acme/company/err.md", "COMP-ACME-ERR", "TEAM-ACME-ERR", "carry ['COMP-ACME', 'TEAM-ACME']"),
            (".harness/standards/test.md", "APP-TEST", "TEAM-ACME-TEST", "must all carry one of APP"),
            (".agents/harnesswright/rules/java/test.md", "JAVA-TEST", "KOTLIN-TEST", "must all carry one of JAVA"),
            ("../acme/team/log.md", "TEAM-ACME-LOG", "COMP-ACME-LOG", "one company, then department, then team"),
        ]
        for rel, old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.files[rel] = self.files[rel].replace(old, new)
                self.write(rel, self.files[rel])
                self.assertStops(expected)

    def test_layers_listed_out_of_order_stop(self):
        self.edit(".harness/profile.yaml", "../acme/company/", "../acme/TEMP/")
        self.edit(".harness/profile.yaml", "../acme/team/", "../acme/company/")
        self.edit(".harness/profile.yaml", "../acme/TEMP/", "../acme/team/")
        self.edit(".harness/profile.yaml", '"2.1.0"', '"X"')
        self.edit(".harness/profile.yaml", '"1.0.0"', '"2.1.0"')
        self.edit(".harness/profile.yaml", '"X"', '"1.0.0"')
        self.assertStops("one company, then department, then team")

    def test_rules_across_layers(self):
        cases = [
            ("../acme/team/log.md", rule("TEAM-ACME-LOG-01"), rule("TEAM-ACME-LOG-01", applies="astronaut"),
             "roles not in the release's roles.md: ['astronaut']"),
            ("../acme/company/work.md", "Tightens:** CORE-WORK-01", "Tightens:** CORE-WORK-99",
             "Tightens CORE-WORK-99, which no more general layer holds active"),
            ("../acme/company/work.md", "Tightens:** CORE-WORK-01", "Tightens:** CORE-SKILL-02",
             "Tightens CORE-SKILL-02, which no more general layer holds active"),
            ("../acme/company/work.md", "- **Kind:** floor", "- **Kind:** choice",
             "Tightens may not go from a choice to a floor"),
            (".harness/standards/test.md", "Overrides:** JAVA-TEST-01", "Overrides:** CORE-WORK-01",
             "Overrides may not go from a idiom to a floor"),
            ("../acme/company/code.md", "BOILERPLATE: records", "BOILERPLATE: getters",
             "option 'getters' is not one of JAVA-DP-BOILERPLATE's Options"),
            ("../acme/company/code.md", "- **Kind:** choice", "- **Kind:** idiom",
             "Binds may not go from a idiom to a decision point"),
            (".harness/standards/test.md", "Overrides:** JAVA-TEST-01", "Overrides:** APP-TEST-02",
             "Overrides APP-TEST-02, which no more general layer holds active"),
        ]
        for rel, old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit(rel, old, new)
                self.assertStops(expected)
        self.setUp()
        self.write("../acme/team/err.md", area("COMP-ACME-ERR", rule("COMP-ACME-ERR-01")))
        self.assertStops("must all carry one of")

    def test_an_id_cannot_be_in_two_layers(self):
        self.write(".harness/standards/dup.md", area("APP-TEST", rule("APP-TEST-01", "idiom")))
        self.assertStops("APP-TEST-01 already defined")
        self.setUp()
        self.edit(".harness/profile.yaml", "../acme/team/", "../acme/company/")
        self.edit(".harness/profile.yaml", '"1.0.0"', '"2.1.0"')
        self.assertStops("one company, then department, then team")

    def test_a_decisions_key_that_names_two_points_stops(self):
        self.write(".agents/harnesswright/rules/kotlin/dp.md", area("KOTLIN-DP", POINT.replace("JAVA", "KOTLIN")))
        self.edit(".harness/profile.yaml", "[java]", "[java, kotlin]")
        self.assertStops("decisions key 'boilerplate' names 2 active decision points")

    def test_decisions_and_waivers(self):
        cases = [
            ("  boilerplate: lombok", "  boilerplate: getters", "option 'getters' is not one of JAVA-DP-BOILERPLATE"),
            ("  boilerplate: lombok", "  mapping: mapstruct", "decisions key 'mapping' names 0 active decision"),
            ("  - rule: COMP-ACME-ERR-01", "  - rule: COMP-ACME-ERR-09", "waiver of COMP-ACME-ERR-09, which no layer"),
            ("  - rule: COMP-ACME-ERR-01", "  - rule: COMP-ACME-WORK-01", "a floor; a floor is never waived"),
            ("    until: 2027-03-01", "    until: 2027-02-30", "'2027-02-30' is not an allowed until"),
        ]
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit(".harness/profile.yaml", old, new)
                self.assertStops(expected)

    def test_the_command_line(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = resolve.main(["--repo", str(self.repo), "--run", "r1", "--date", "2026-11-12"])
        self.assertEqual((code, "inputs checked" in err.getvalue()), (2, True))
        self.edit(".harness/profile.yaml", '"0.1.0"', '"9.9.9"')
        with redirect_stderr(err):
            code = resolve.main(["--repo", str(self.repo), "--run", "r1", "--date", "2026-11-12"])
        self.assertEqual((code, "resolve stopped: release" in err.getvalue()), (1, True))
        (self.repo / resolve.PROFILE).unlink()
        with redirect_stderr(err):
            code = resolve.main(["--repo", str(self.repo), "--run", "r1", "--date", "2026-11-12"])
        self.assertEqual((code, "profile.yaml: is missing or cannot be read" in err.getvalue()), (1, True))


if __name__ == "__main__":
    unittest.main()
