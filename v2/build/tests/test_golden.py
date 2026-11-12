"""The build against a hand-written golden release. Run: python3 -m unittest discover -s v2/build/tests

golden/root is a small fixture repository: a CORE layer with multi-line parts, a code block with a blank line, a
nested Source list, IDs where one is a prefix of another (CORE-TEST-01, CORE-TEST-011), a retired, an inferred, an
Exceptions and an Overrides case (CORE-TEST-04, which reaches only because it overrides a cited rule), two
decision points (one cited, one reaching only by role), and a language-layer rule the build
must ignore. golden/expected was written by hand, not by the build; its hash and sizes were computed from its own
text. The build must give exactly these files, plus scripts/, rules/ (every layer folder) and roles.md copied byte
for byte from their sources.
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
        built = {path: text for path, text in self.files.items() if not build.is_copy(path)}
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

    def test_layers_and_roles_file_are_their_sources(self):
        """Every layer folder, the language layer too, and no folder index the fixture lacks."""
        copied = {path: data for path, data in self.files.items() if build.is_copy(path) and "/scripts/" not in path}
        sources = {f"rules/{p.parent.name}/{p.name}": p for p in (GOLDEN / "root/v2/rules").glob("*/*")}
        self.assertEqual(sorted(copied), sorted([*sources, "roles.md"]))
        self.assertIn("rules/java/test.md", copied)
        for path, data in copied.items():
            with self.subTest(path=path):
                source = GOLDEN / "root/v2/roles.md" if path == "roles.md" else sources[path]
                self.assertEqual(data, source.read_bytes())

    def test_rules_that_must_not_be_copied(self):
        """The first four do not reach; CORE-DP-STACK reaches by role only, so it is not copied into the skill."""
        text = "".join(t for p, t in self.files.items() if isinstance(t, str) and not build.is_copy(p))
        for rule_id in ("JAVA-TEST-01", "CORE-TEST-02", "CORE-TEST-03", "CORE-WORK-02", "CORE-DP-STACK"):
            with self.subTest(rule=rule_id):
                self.assertNotIn(rule_id, text)


if __name__ == "__main__":
    unittest.main()
