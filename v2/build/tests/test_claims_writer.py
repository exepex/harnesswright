"""Tests for the claims writer template's reference. Run: python3 -m unittest discover -s v2/build/tests

The reference holds the claims contract unchanged between two `~~~~` lines, so the skill and the story judge read
the same layout (plan/b2-plan.md, B2a).
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "v2" / "skills" / "claims-writer" / "references" / "claims-template.md"
CONTRACT = ROOT / "contracts" / "claims.md"


class ReferenceTest(unittest.TestCase):
    def test_the_reference_holds_the_contract_unchanged(self):
        text = REFERENCE.read_text(encoding="utf-8")
        parts = text.split("~~~~markdown\n")
        self.assertEqual(len(parts), 2, "the reference has one ~~~~markdown fence")
        self.assertTrue(parts[1].endswith("~~~~\n"), "the fence closes at the end of the file")
        self.assertEqual(parts[1].removesuffix("~~~~\n"), CONTRACT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
