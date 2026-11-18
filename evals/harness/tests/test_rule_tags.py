"""The kit's own reader of rule tags (`evals/checks/tags.py`) against the bad and plain lines every reader shares,
`v2/build/tests/golden/tag-faults.md`: each template line fails `rule_tags`, each plain line passes, and each
failure names the line."""

import json

from helpers import TempCase

import checks
from cases import REPO

FAULTS = REPO / "v2" / "build" / "tests" / "golden" / "tag-faults.md"
KEY = json.loads((checks.KEYS / "rule_tags" / "tags-pass.json").read_text(encoding="utf-8"))
FILE = KEY["args"]["file"]


def faults(heading):
    """The example lines under one `##` heading of the shared faults file."""
    lines = FAULTS.read_text(encoding="utf-8").split("\n")
    start = lines.index(f"## {heading}") + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return [line for line in lines[start:end] if line]


def decide(added):
    """`rule_tags` on the passing key's template with `added` as its last lines, the index also listing the
    golden layer's CORE-TEST-01, which the shared lines cite."""
    key = json.loads(json.dumps(KEY))
    for side in ("before", "after"):
        key[side]["v2/rules/index.md"] += "| CORE-TEST-01 | A test names its scenario |\n"
    key["after"][FILE] += added + "\n"
    return checks.decide("rule_tags", checks.Bundle.key(key), {**KEY["args"], "require": []})


class SharedFaults(TempCase):
    def test_the_shared_lines_are_there(self):
        self.assertEqual([len(faults(h)) for h in ("Template lines", "Plain lines")], [21, 4])

    def test_each_bad_template_line_fails_and_is_named(self):
        number = KEY["after"][FILE].count("\n") + 1
        for line in faults("Template lines"):
            with self.subTest(line=line):
                verdict = decide(line)
                self.assertEqual(verdict["outcome"], "fail")
                self.assertTrue(verdict["reason"].startswith(f"{FILE}:{number}: "), verdict["reason"])

    def test_the_plain_lines_pass(self):
        verdict = decide("\n".join(faults("Plain lines")))
        self.assertEqual(verdict["outcome"], "pass", verdict["reason"])
