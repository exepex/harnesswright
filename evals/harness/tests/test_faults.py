"""The fault catalogue: every harness fault names a test that plants it, and that test exists."""

import importlib
import json
import unittest

import helpers  # noqa: F401  (puts the harness on the path)
from cases import REPO


class Catalogue(unittest.TestCase):
    def test_every_fault_has_a_planting_test(self):
        catalogue = json.loads((REPO / "evals" / "faults" / "harness.json").read_text())
        ids = [fault["id"] for fault in catalogue["faults"]]
        self.assertEqual(len(ids), len(set(ids)))
        for fault in catalogue["faults"]:
            module, cls, method = fault["test"].split(".")
            with self.subTest(fault["id"]):
                test_class = getattr(importlib.import_module(module), cls)
                self.assertTrue(callable(getattr(test_class, method, None)), fault["test"])
                self.assertTrue(method.startswith(f"test_{fault['id'].lower().replace('-', '')}_"), fault["test"])


if __name__ == "__main__":
    unittest.main()
