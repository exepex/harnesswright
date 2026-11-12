"""Tests for repoprofile.py (B0.1 part e1a): reading the profile and layer.yaml.
Run: python3 -m unittest discover -s v2/build/tests

ProfileTest starts from a valid profile and layer.yaml, breaks one thing and asserts the message that names it.
"""

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "v2" / "build"))

import repoprofile  # noqa: E402

PROFILE = """# a comment line
harnesswright:                        # the release
  version: "0.1.0"
  folder: .agents/harnesswright/

standards:
  languages: [java]
  layers:
    - name: acme
      folder: ../acme/company/
      version: "2.1.0"
    - name: acme
      folder: ../acme/team/
      version: "1.0.0"
  repository: .harness/standards/

waivers:
  - rule: COMP-ACME-ERR-01
    reason: legacy endpoints keep the old error format
    until: 2027-03-01
    approved by: app-owner, acme-owner
  - rule: TEAM-ACME-LOG-01
    reason: old logger
    until: 2026-01-01
    approved by: app-owner

rules-text-limit: 45000

decisions:
  boilerplate: lombok

models:
  deep: anything at all: here
"""



class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.tmp / "app"
        self.files = {".harness/profile.yaml": PROFILE,
                      "../acme/team/layer.yaml": "owner: Acme payments team\nversion: \"1.0.0\"\n"}
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
        return repoprofile.read_profile(self.repo / repoprofile.PROFILE)

    def assertStops(self, line, expected):
        with self.assertRaises(repoprofile.RulebookError) as caught:
            self.load()
        self.assertRegex(str(caught.exception), rf"profile\.yaml:{line}: (?:.* )?{re.escape(expected)}")

    def test_a_valid_profile_is_read_and_other_sections_skipped(self):
        profile = self.load()
        self.assertEqual((profile["version"], profile["folder"]), ("0.1.0", ".agents/harnesswright/"))
        self.assertEqual(profile["languages"], ["java"])
        self.assertEqual([(x["folder"], x["version"]) for x in profile["layers"]],
                         [("../acme/company/", "2.1.0"), ("../acme/team/", "1.0.0")])
        self.assertEqual(profile["repository"], ".harness/standards/")
        self.assertEqual([(w["rule"], w["until"], w["line"]) for w in profile["waivers"]],
                         [("COMP-ACME-ERR-01", "2027-03-01", 18), ("TEAM-ACME-LOG-01", "2026-01-01", 22)])
        self.assertEqual(profile["waivers"][0]["approved by"], "app-owner, acme-owner")
        self.assertEqual((profile["limit"], profile["decisions"]), (45000, {"boilerplate": ("lombok", 30)}))
        self.edit(".harness/profile.yaml", "    reason: old logger", '    reason: "see ticket # 12"  # why')
        self.assertEqual(self.load()["waivers"][1]["reason"], "see ticket # 12")
        self.edit(".harness/profile.yaml", "rules-text-limit: 45000\n", "")
        self.assertEqual(self.load()["limit"], 30000)

    def test_other_allowed_forms(self):
        self.write(".harness/profile.yaml", "---\nharnesswright:\n    version: '1.0.0'\n    folder: hw/\n"
                   "standards:\n    languages:\n      - java\n      - java-spring\n    layers: []\n"
                   "    repository: 'app/'  \n"
                   "waivers: []\ndecisions: {}\n")
        profile = self.load()
        self.assertEqual((profile["version"], profile["languages"]), ("1.0.0", ["java", "java-spring"]))
        self.assertEqual((profile["layers"], profile["waivers"], profile["decisions"]), ([], [], {}))
        path = self.repo / repoprofile.PROFILE
        block = "languages:\n      - java\n      - java-spring"
        path.write_text(path.read_text().replace(block, "languages: [\"java\", 'java-spring']"))
        self.assertEqual(self.load()["languages"], ["java", "java-spring"])

    def test_doc_07_example_is_read(self):
        doc = (ROOT / "docs/design/07-repo-profile.md").read_text(encoding="utf-8").split("\n")
        start = doc.index("```yaml") + 1
        self.write(".harness/profile.yaml", "\n".join(doc[start:doc.index("```", start)]) + "\n")
        profile = self.load()
        self.assertEqual((profile["version"], profile["languages"]), ("1.4.0", ["java", "java-spring"]))
        self.assertEqual(profile["layers"],
                         [{"name": "acme", "folder": "../acme-rules/", "version": "2.1.0", "line": 9}])
        self.assertEqual([(w["rule"], w["line"]) for w in profile["waivers"]], [("COMP-ACME-ERR-03", 15)])
        self.assertEqual((profile["limit"], sorted(profile["decisions"])),
                         (45000, ["boilerplate", "construction", "mapping"]))

    def test_profile_shapes(self):
        cases = [  # old text, new text, the line the stop names, its message
            ('  version: "0.1.0"\n', '  version: "0.1.0"\n  version: "0.1.0"\n', 4, "'version' appears twice"),
            ('  version: "0.1.0"\n', '  version: "0.1.0"\n  channel: beta\n', 4, "'channel' is not allowed"),
            ("  folder: .agents/harnesswright/\n", "", 2, "missing folder"),
            ("  folder: .agents/harnesswright/", "  folder: /abs path/", 4, "'/abs path/' is not an allowed folder"),
            ("  folder: .agents/harnesswright/", "\tfolder: x/", 4, "line has no allowed shape here"),
            ("  repository: .harness/standards/\n", "  repository: .harness/standards/\n  extra: x\n", 16,
             "'extra' is not allowed here"),
            ("standards:", "standard:", 6, "'standard' is not a section"),
            ("  layers:", "layers:", 8, "'layers' is not a section"),
            ("  languages: [java]", "  languages: java", 7, "expected a list of language names"),
            ("  languages: [java]", "  languages: [Java]", 7, "'Java' is not an allowed language"),
            ("  languages: [java]", "  languages: [java, ]", 7, "has an empty item"),
            ("    - name: acme\n      folder: ../acme/company/", "    - folder: ../acme/company/", 9, "missing name"),
            ("    - name: acme\n      folder: ../acme/company/", "    - name: Acme-co\n      folder: ../acme/company/",
             9, "'Acme-co' is not an allowed name"),
            ("      folder: ../acme/team/", "       folder: ../acme/team/", 13, "not indented like"),
            ("  layers:\n", "  layers:\n    name: x\n", 10, "a block mixes list items and keys"),
            ("COMP-ACME-ERR-01", "comp-acme-err-01", 18, "'comp-acme-err-01' is not an allowed rule"),
            ("    reason: old logger\n", "", 22, "missing reason"),
            ("    reason: old logger", '    reason: "old logger', 23, "must end with its quote"),
            ("    reason: old logger", '    reason: "old\\u0020logger"', 23, "has no escapes"),
            ("    reason: old logger", "    reason: 'it''s old'", 23, "must end with its quote"),
            ("    reason: old logger", "    reason: {old: logger}", 23, "must be quoted"),
            ("    reason: old logger", "    reason: &old logger", 23, "must be quoted"),
            ("    reason: old logger", "    reason: *old", 23, "must be quoted"),
            ("    reason: old logger", "    reason: no", 23, "must be quoted"),
            ("    reason: old logger", '    reason: "old\tlogger"', 23, "is not an allowed reason"),
            ("    until: 2026-01-01", "    until: soon", 24, "'soon' is not an allowed until"),
            ("    until: 2026-01-01", "    until: 2027-02-30", 24, "'2027-02-30' is not an allowed until"),
            ("    approved by: app-owner\n", "    approved by: \n", 25, "'approved by' has no value"),
            ("app-owner, acme-owner", '"@app-owner"', 21, "'@app-owner' is not an allowed approved by"),
            ("TEAM-ACME-LOG-01", "COMP-ACME-ERR-01", 22, "already has a waiver on line 18"),
            ("rules-text-limit: 45000", "rules-text-limit: 60001", 27, "over the maximum of 60000"),
            ("rules-text-limit: 45000", "rules-text-limit: 0", 27, "'0' is not an allowed limit"),
            ("rules-text-limit: 45000\n", "rules-text-limit: 45000\n  extra: 1\n", 28, "not indented like"),
            ("  boilerplate: lombok", "  boilerplate: Lombok please", 30, "is not an allowed option"),
            ("  boilerplate: lombok", "  boilerplate:\n    deep: x", 30, "expected one option value"),
            ("  boilerplate: lombok", "  a--b: lombok", 30, "'a--b' is not an allowed key"),
            ("  boilerplate: lombok", "  - lombok", 29, "expected one `point: option` line"),
            ("# a comment line\n", "  stray: x\n", 1, "an indented line comes before the first section"),
            ("models:", "- models:", 32, "a top-level line must be `section:`"),
            ("  - rule: TEAM", "- rule: TEAM", 22, "a top-level line must be `section:`"),
            ('  version: "0.1.0"', '\tversion: "0.1.0"', 3, "line has no allowed shape here"),
            ("rules-text-limit: 45000", "rules-text-limit: 60000", 0, ""),
            ("  boilerplate: lombok", "  http2: lombok", 0, ""),
            ("    reason: old logger", '    reason: "old" logger', 23, "must end with its quote"),
            ("  repository: .harness/standards/", "  repository: /abs/", 15, "'/abs/' is not an allowed folder"),
            ("harnesswright:", "release:", 2, "'release' is not a section"),
            ('  version: "0.1.0"\n  folder: .agents/harnesswright/\n', "", 2, "'harnesswright' has no value"),
            ("models:", "decisions:", 32, "'decisions' appears twice"),
        ]
        for old, new, line, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit(".harness/profile.yaml", old, new)
                if line:
                    self.assertStops(line, expected)
                else:
                    self.load()  # an allowed edge value is read

    def test_layer_yaml(self):
        folder = (self.repo / "../acme/team").resolve()
        self.assertEqual(repoprofile.read_layer_yaml("acme", folder, "1.0.0", []), "Acme payments team")
        cases = [('"1.0.0"', '"1.0.1"', "version 1.0.1 is not the profile's 1.0.0"),
                 ("owner: Acme payments team\n", "", "layer.yaml:1: missing owner"),
                 ("owner: Acme payments team\n", "owner: x\nlevel: team\n", "layer.yaml:2: 'level' is not a section")]
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit("../acme/team/layer.yaml", old, new)
                with self.assertRaises(repoprofile.RulebookError) as caught:
                    repoprofile.read_layer_yaml("acme", (self.repo / "../acme/team").resolve(), "1.0.0", [])
                self.assertIn(expected, str(caught.exception))
        for folder in (self.tmp / "gone", self.tmp / "latin1"):
            with self.subTest(folder=folder.name):
                if folder.name == "latin1":
                    folder.mkdir()
                    (folder / "layer.yaml").write_bytes(b"owner: M\xfcller\nversion: \"1.0.0\"\n")
                with self.assertRaises(repoprofile.RulebookError) as caught:
                    repoprofile.read_layer_yaml("acme", folder, "1.0.0", [])
                self.assertIn(f"layer acme: {folder}/layer.yaml: is missing or cannot be read", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
