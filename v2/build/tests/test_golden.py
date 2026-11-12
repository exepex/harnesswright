"""The build against a hand-written golden release. Run: python3 -m unittest discover -s v2/build/tests

golden/root is a small fixture repository: a CORE layer with multi-line parts, a code block with a blank line, a
nested Source list, IDs where one is a prefix of another (CORE-TEST-01, CORE-TEST-011), a retired, an inferred and
an Exceptions case, two decision points (one cited, one reaching only by role), and a language-layer rule the build
must ignore. golden/expected was written by hand, not by the build; its hash and sizes were computed from its own
text. The build must give exactly these files, plus scripts/ copied byte for byte from their sources.
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
sys.path.insert(0, str(HERE.parent))

import build  # noqa: E402


class GoldenTest(unittest.TestCase):
    def setUp(self):
        self.files = build.build(GOLDEN / "root")

    def test_every_file_outside_scripts_matches_the_golden_release(self):
        expected = {p.relative_to(GOLDEN / "expected").as_posix(): p.read_text(encoding="utf-8")
                    for p in (GOLDEN / "expected").rglob("*") if p.is_file()}
        built = {path: text for path, text in self.files.items() if "/scripts/" not in path}
        self.assertEqual(sorted(built), sorted(expected))
        for path, text in expected.items():
            with self.subTest(path=path):
                self.assertEqual(built[path], text)

    def test_scripts_are_their_sources(self):
        scripts = {path: data for path, data in self.files.items() if "/scripts/" in path}
        self.assertEqual(sorted(scripts), [f"golden-skill/scripts/{m}" for m in sorted(build.SHIPPED)])
        for path, data in scripts.items():
            with self.subTest(path=path):
                self.assertEqual(data, (HERE.parent / Path(path).name).read_bytes())

    def test_rules_that_must_not_reach(self):
        text = "".join(t for t in self.files.values() if isinstance(t, str))
        for rule_id in ("JAVA-TEST-01", "CORE-TEST-02", "CORE-TEST-03", "CORE-WORK-02", "CORE-DP-STACK"):
            with self.subTest(rule=rule_id):
                self.assertNotIn(rule_id, text)


if __name__ == "__main__":
    unittest.main()
