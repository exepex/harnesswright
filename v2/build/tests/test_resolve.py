"""Tests for resolve.py part e1a: reading the profile and layer.yaml. Run: python3 -m unittest discover -s v2/build/tests

Each test starts from a valid profile and layer.yaml, breaks one thing and asserts the message that names it.
"""

import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "v2" / "build"))

import resolve  # noqa: E402

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
        return resolve.read_profile(self.repo / resolve.PROFILE)

    def assertStops(self, expected):
        with self.assertRaises(resolve.RulebookError) as caught:
            self.load()
        self.assertIn(expected, str(caught.exception))

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
        self.edit(".harness/profile.yaml", "rules-text-limit: 45000\n", "")
        self.assertEqual(self.load()["limit"], 30000)

    def test_profile_shapes(self):
        cases = [
            ('  version: "0.1.0"\n', '  version: "0.1.0"\n  version: "0.1.0"\n', "'version' appears twice"),
            ('  folder: .agents/harnesswright/\n', "", "missing ['folder']"),
            ("  repository: .harness/standards/\n", "  repository: .harness/standards/\n  extra: x\n",
             "not allowed ['extra']"),
            ("  languages: [java]", "  languages: java", "languages is a list written as [a, b]"),
            ("  languages: [java]", "  languages: [Java]", "'Java' is not an allowed language"),
            ("    reason: old logger\n", "", "missing ['reason']"),
            ("    until: 2026-01-01", "    until: soon", "'soon' is not an allowed until"),
            ("    approved by: app-owner\n", "    approved by: \n", "line has no allowed shape here"),
            ("rules-text-limit: 45000", "rules-text-limit: 60001", "over the maximum of 60000"),
            ("rules-text-limit: 45000", "rules-text-limit: lots", "'lots' is not an allowed limit"),
            ("  boilerplate: lombok", "  boilerplate: Lombok please", "is not an allowed option"),
            ("      folder: ../acme/team/", "       folder: ../acme/team/", "line has no allowed shape here"),
            ("  layers:\n", "  layers:\n    name: x\n", "line has no allowed shape here"),
        ]
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit(".harness/profile.yaml", old, new)
                self.assertStops(expected)

    def test_layer_yaml(self):
        folder = (self.repo / "../acme/team").resolve()
        self.assertEqual(resolve.read_layer_yaml("acme", folder, "1.0.0", []), "Acme payments team")
        cases = [('"1.0.0"', '"1.0.1"', "version 1.0.1 is not the profile's 1.0.0"),
                 ("owner: Acme payments team\n", "", "missing ['owner']"),
                 ("owner: Acme payments team\n", "owner: x\nlevel: team\n", "not allowed ['level']")]
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                self.edit("../acme/team/layer.yaml", old, new)
                with self.assertRaises(resolve.RulebookError) as caught:
                    resolve.read_layer_yaml("acme", (self.repo / "../acme/team").resolve(), "1.0.0", [])
                self.assertIn(expected, str(caught.exception))
        with self.assertRaises(resolve.RulebookError) as caught:
            resolve.read_layer_yaml("acme", self.tmp / "gone", "1.0.0", [])
        self.assertIn("layer acme: ", str(caught.exception))

    def test_the_command_line(self):
        err = io.StringIO()
        args = ["--repo", str(self.repo), "--run", "r1", "--date", "2026-11-12"]
        with redirect_stderr(err):
            self.assertEqual(resolve.main(args), 2)
        self.edit(".harness/profile.yaml", '"0.1.0"', "zero")
        with redirect_stderr(err):
            self.assertEqual(resolve.main(args), 1)
        self.assertIn("resolve stopped: ", err.getvalue())


if __name__ == "__main__":
    unittest.main()
