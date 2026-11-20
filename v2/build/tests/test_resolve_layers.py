"""Tests for resolve.py part e1a: reading and checking the layers. Run: python3 -m unittest discover -s v2/build/tests

LayersTest starts from a valid application: the real release (CORE and roles.md), a java language layer with a
decision point, an acme company layer, an acme team layer and application rules, with test_repoprofile's profile. Each
test breaks one thing and asserts the message that names it.
"""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import date
from pathlib import Path

from test_repoprofile import PROFILE, ROOT  # puts v2/build on sys.path

import build  # noqa: E402
import resolve  # noqa: E402

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


class Application(unittest.TestCase):
    """A valid application to break: the base of the layer and rules.md tests; it holds no test itself."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.tmp / "app"
        release = self.repo / ".agents/harnesswright"
        shutil.copytree(ROOT / "release", release)
        # The fixture is the release at 0.1.0 with no skills, whatever v2/VERSION and v2/skills hold now.
        for skill in [p for p in release.iterdir() if p.is_dir() and p.name != "rules"]:
            shutil.rmtree(skill)
        manifest = {"rulebook-version": "0.1.0", "run-time": list(build.RUN_TIME), "skills": {}}
        (release / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        roles = (release / "roles.md").read_text(encoding="utf-8")
        jobs = "| Job | Roles | Skills in order | `rest` skill |\n|---|---|---|---|\n"
        (release / "roles.md").write_text(roles[:roles.index(jobs) + len(jobs)], encoding="utf-8")
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


class LayersTest(Application):
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
        release = (self.repo / ".agents/harnesswright").resolve()
        listed = json.loads((release / "manifest.json").read_text())["run-time"]
        for path in inputs.files[1:]:  # every read of the release is on the run-time list its manifest ships
            rel = Path(path).resolve().relative_to(release).as_posix() if release in Path(path).resolve().parents \
                else None
            if rel is not None:
                self.assertTrue(any(rel == p or (p.endswith("/") and rel.startswith(p)) for p in listed), rel)

    def test_a_release_read_off_its_run_time_list_stops(self):
        for listed, expected in ((["manifest.json", "rules/"], "roles.md is not on the run-time list"),
                                 (["manifest.json", "roles.md"], "rules/core is not on the run-time list")):
            with self.subTest(listed=listed):
                self.setUp()
                path = self.repo / ".agents/harnesswright/manifest.json"
                data = json.loads(path.read_text())
                path.write_text(json.dumps(dict(data, **{"run-time": listed})) + "\n")
                self.assertStops(expected)

    def test_release_and_layer_versions_and_folders(self):
        cases = [
            (".harness/profile.yaml", '  version: "0.1.0"', '  version: "0.2.0"', "version 0.1.0 is not the profile's"),
            (".harness/profile.yaml", "  folder: .agents/harnesswright/", "  folder: elsewhere/",
             "manifest.json is missing"),
            (".harness/profile.yaml", "[java]", "[java, kotlin]", "layer kotlin: folder"),
            (".harness/profile.yaml", "../acme/team/", "../acme/gone/",
             "acme/gone/layer.yaml: is missing or cannot be read"),
            (".harness/profile.yaml", "  repository: .harness/standards/", "  repository: nowhere/",
             "layer application: folder"),
        ]
        for rel, old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit(rel, old, new)
                self.assertStops(expected)
        self.setUp()
        self.write(".agents/harnesswright/manifest.json", "not json\n")
        self.assertStops("manifest.json is missing or cannot be read")

    def test_layer_prefixes_and_order(self):
        cases = [
            ("../acme/team/log.md", "TEAM-ACME-LOG", "TEAM-OTHER-LOG", "must all carry one of COMP-ACME"),
            ("../acme/company/err.md", "COMP-ACME-ERR", "TEAM-ACME-ERR", "carry ['COMP-ACME', 'TEAM-ACME']"),
            (".harness/standards/test.md", "APP-TEST", "TEAM-ACME-TEST", "must all carry one of APP"),
            (".agents/harnesswright/rules/java/test.md", "JAVA-TEST", "KOTLIN-TEST", "must all carry one of JAVA"),
            ("../acme/team/log.md", "TEAM-ACME-LOG", "COMP-ACME-LOG", "carries COMP-ACME, which"),
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
        self.assertStops("profile.yaml:12: layer acme")
        self.assertStops("is a COMP layer listed after a TEAM layer")

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
            (".harness/standards/test.md", "- **Kind:** idiom", "- **Kind:** floor",
             "Overrides may not go from a floor to a idiom"),
        ]
        for rel, old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit(rel, old, new)
                self.assertStops(expected)
        self.setUp()
        self.write("../acme/team/err.md", area("COMP-ACME-ERR", rule("COMP-ACME-ERR-01")))
        self.assertStops("must all carry one of")

    def test_each_layer_is_read_once_and_readable(self):
        java = ".agents/harnesswright/rules/java/test.md"
        cases = [
            (".harness/profile.yaml", "[java]", "[java, java]", "carries JAVA, which"),
            (".harness/profile.yaml", "[java]", "[core, java]", "carries CORE, which"),
            (".harness/profile.yaml", "[java]", "[java-spring, java]", "profile.yaml:7: standards.languages lists framework java-spring"),
            (java, "- **Status:** active", "- **Status:** inferred", "Overrides JAVA-TEST-01, which no more general"),
            (java, "**Applies to:** implementer", "**Applies to:** astronaut", "roles not in the release's roles.md"),
            ("../acme/company/err.md", "**Status:** active", "**Status:** inferred",
             "waiver of COMP-ACME-ERR-01, which"),
            ("../acme/company/work.md", "Tightens:** CORE-WORK-01", "Overrides:** APP-TEST-01",
             "Overrides APP-TEST-01, which no more general layer holds active"),
        ]
        for rel, old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit(rel, old, new)
                self.assertStops(expected)
        for broken, expected in ((".harness/standards/test.md", "holds no rule file"),
                                 (".agents/harnesswright/roles.md", "roles.md is missing or cannot be read")):
            with self.subTest(expected=expected):
                self.setUp()
                (self.repo / broken).unlink()
                self.assertStops(expected)
        self.setUp()
        (self.repo / "../acme/team/log.md").resolve().write_bytes(b"# TEAM-ACME-LOG \xb7 Caf\xe9\n")
        self.assertStops("log.md cannot be read (UnicodeDecodeError)")

    def test_an_id_cannot_be_in_two_layers(self):
        self.write(".harness/standards/dup.md", area("APP-TEST", rule("APP-TEST-01", "idiom")))
        self.assertStops("APP-TEST-01 already defined")
        self.setUp()
        self.edit(".harness/profile.yaml", "../acme/team/", "../acme/company/")
        self.edit(".harness/profile.yaml", '"1.0.0"', '"2.1.0"')
        self.assertStops("carries COMP-ACME, which")

    def test_a_decisions_key_names_one_point_per_stack(self):
        self.write(".agents/harnesswright/rules/kotlin/dp.md", area("KOTLIN-DP", POINT.replace("JAVA", "KOTLIN")))
        self.edit(".harness/profile.yaml", "[java]", "[java, kotlin]")
        self.assertEqual(self.load().decisions, {"JAVA-DP-BOILERPLATE": ("lombok", 30),
                                                 "KOTLIN-DP-BOILERPLATE": ("lombok", 30)})
        self.write(".agents/harnesswright/rules/core/dp.md", area("CORE-DP", POINT.replace("JAVA", "CORE")))
        self.assertStops("names 2 active decision points in one stack (CORE-DP-BOILERPLATE, JAVA-DP-BOILERPLATE)")

    def test_decisions_and_waivers(self):
        cases = [
            ("  boilerplate: lombok", "  boilerplate: getters", "option 'getters' is not one of JAVA-DP-BOILERPLATE"),
            ("  boilerplate: lombok", "  mapping: mapstruct", "decisions key 'mapping' names 0 active decision"),
            ("  - rule: COMP-ACME-ERR-01", "  - rule: COMP-ACME-ERR-09", "waiver of COMP-ACME-ERR-09, which no layer"),
            ("  - rule: COMP-ACME-ERR-01", "  - rule: COMP-ACME-WORK-01", "COMP-ACME-WORK-01, a floor; only a"),
            ("  - rule: COMP-ACME-ERR-01", "  - rule: COMP-ACME-CODE-01", "COMP-ACME-CODE-01, a binding; only a"),
            ("  - rule: COMP-ACME-ERR-01", "  - rule: JAVA-DP-BOILERPLATE", "a decision point; only a principle"),
            ("  boilerplate: lombok", "  boilerplate: lombok\n  stack: x", "decisions key 'stack' names 0 active"),
            ("    until: 2027-03-01", "    until: 2027-02-30", "'2027-02-30' is not an allowed until"),
        ]
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit(".harness/profile.yaml", old, new)
                self.assertStops(expected)

    def test_a_rule_changes_only_a_more_general_layer(self):
        self.write(".harness/standards/more.md", area("APP-MORE", rule("APP-MORE-01", "idiom",
                                                                      "- **Overrides:** APP-TEST-01\n")))
        self.assertStops("Overrides APP-TEST-01, which no more general layer holds active")
        self.setUp()
        self.edit("../acme/company/err.md", "- **Kind:** choice",
                  "- **Kind:** choice\n- **Overrides:** TEAM-ACME-LOG-01")
        self.assertStops("Overrides TEAM-ACME-LOG-01, which no more general layer holds active")

    def test_a_department_layer_sits_between_company_and_team(self):
        team = "    - name: acme\n      folder: ../acme/team/\n      version: \"1.0.0\"\n"
        dept = team.replace("team", "dept")
        for order, expected in ((dept + team, None), (team + dept, "is a DEPT layer listed after a TEAM layer"),
                                (team + team, "carries TEAM-ACME, which")):
            with self.subTest(expected=expected):
                self.setUp()
                self.write("../acme/dept/layer.yaml", "owner: Acme payments department\nversion: \"1.0.0\"\n")
                self.write("../acme/dept/err.md", area("DEPT-ACME-ERR", rule("DEPT-ACME-ERR-01")))
                self.edit(".harness/profile.yaml", team, order)
                if expected:
                    self.assertStops(expected)
                else:
                    self.assertEqual([s.prefix for s in self.load().sources][2:5],
                                     ["COMP-ACME", "DEPT-ACME", "TEAM-ACME"])

    def test_two_company_layers_stop(self):
        self.write("../acme/team/log.md", area("COMP-OTHER-LOG", rule("COMP-OTHER-LOG-01")))
        self.edit(".harness/profile.yaml", "    - name: acme\n      folder: ../acme/team/",
                  "    - name: other\n      folder: ../acme/team/")
        self.edit(".harness/profile.yaml", "TEAM-ACME-LOG-01", "COMP-OTHER-LOG-01")
        self.assertStops("profile.yaml:12: layer other")
        self.assertStops("is a COMP layer listed after a COMP layer")

    def test_a_framework_reads_after_its_language(self):
        self.write(".agents/harnesswright/rules/java-spring/web.md", area("JAVA-SPRING-WEB", rule(
            "JAVA-SPRING-WEB-01", "idiom", "- **Overrides:** JAVA-TEST-01\n")))
        self.edit(".harness/profile.yaml", "[java]", "[java, java-spring]")
        self.assertEqual([s.prefix for s in self.load().sources][:3], ["CORE", "JAVA", "JAVA-SPRING"])

    def test_each_relation_goes_only_between_allowed_kinds(self):
        kinds = ("floor", "principle", "idiom", "choice")
        for relation in ("Overrides", "Tightens"):
            for source in kinds:
                for target in kinds:
                    with self.subTest(relation=relation, source=source, target=target):
                        self.setUp()
                        self.edit(".agents/harnesswright/rules/java/test.md", "- **Kind:** idiom",
                                  f"- **Kind:** {target}")
                        self.edit(".harness/standards/test.md", "- **Kind:** idiom\n",
                                  f"- **Kind:** {source}\n")
                        self.edit(".harness/standards/test.md", "Overrides:** JAVA", f"{relation}:** JAVA")
                        changeable = ("principle", "idiom", "choice")  # doc 03 HW-RULE-05, written out here
                        allowed = (source == target == "floor" if relation == "Tightens"
                                   else source in changeable and target in changeable)
                        if allowed:
                            self.load()
                        else:
                            self.assertStops(f"{relation} may not go from a {source} to a {target}")

    def test_a_waiver_applies_through_its_until_date(self):
        self.edit(".harness/profile.yaml", "    until: 2026-01-01", "    until: 2026-11-12")
        inputs = self.load()
        self.assertEqual([w["rule"] for w in inputs.waivers], ["COMP-ACME-ERR-01", "TEAM-ACME-LOG-01"])
        self.assertEqual(inputs.expired, [])
        self.edit(".agents/harnesswright/rules/java/dp.md", "- **Status:** active", "- **Status:** inferred")
        self.assertStops("Binds JAVA-DP-BOILERPLATE, which no more general layer holds active")
        self.edit("../acme/company/code.md", "- **Binds:** JAVA-DP-BOILERPLATE: records\n", "")
        self.assertStops("decisions key 'boilerplate' names 0 active decision points")

    def test_the_command_line(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = resolve.main(["--repo", str(self.repo), "--run", "r1", "--date", "2026-11-12"])
        self.assertEqual((code, "and 0 rules texts" in err.getvalue()), (0, True))
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
