"""Rule tags and `Rules:` lines, read by the build and by the release check. Run:
python3 -m unittest discover -s v2/build/tests

The good examples are the golden skill (golden/root and its hand-written release golden/expected, test_golden.py).
The bad ones are golden/tag-faults.md, shared by every reader of rule tags.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
sys.path.insert(0, str(HERE.parent))

import build  # noqa: E402
import check_rules  # noqa: E402

SKILL = "v2/skills/golden-skill/SKILL.tmpl.md"


def faults(heading):
    """The bad lines under one heading of golden/tag-faults.md."""
    lines = (GOLDEN / "tag-faults.md").read_text(encoding="utf-8").split("\n")
    start = lines.index(f"## {heading}") + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return [line for line in lines[start:end] if line]


class TagTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root, self.release = self.tmp / "root", self.tmp / "release"
        shutil.copytree(GOLDEN / "root", self.root)
        shutil.copytree(GOLDEN / "expected", self.release)

    def append(self, path, line):
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def test_the_shared_faults_are_there(self):
        self.assertEqual([len(faults(h)) for h in ("Template lines", "Release lines", "Plain lines")], [18, 12, 4])

    def test_the_build_fails_each_bad_template_line_and_names_it(self):
        lines = (self.root / SKILL).read_text(encoding="utf-8").count("\n")
        for line in faults("Template lines"):
            with self.subTest(line=line):
                self.setUp()
                self.append(self.root / SKILL, line)
                with self.assertRaisesRegex(build.tags.TagError, f"golden-skill/SKILL.tmpl.md:{lines + 1}: "):
                    build.build(self.root)

    def test_the_build_fails_a_bad_line_in_a_reference_too(self):
        self.append(self.root / "v2/skills/golden-skill/references/guide.md", faults("Template lines")[0])
        with self.assertRaisesRegex(build.tags.TagError, "references/guide.md:3: a rule tag stands only on"):
            build.build(self.root)

    def test_the_release_check_fails_each_bad_release_line_at_that_line(self):
        self.assertEqual(check_rules.Check(self.root, self.release).run(), [])
        skill = self.release / "golden-skill/SKILL.md"
        at = f"release/golden-skill/SKILL.md:{skill.read_text(encoding='utf-8').count(chr(10)) + 1}: "
        reasons = ("holds a rule tag the build did not write out", "a `Rules:` line holds only", "is bare")
        for line in faults("Release lines"):
            with self.subTest(line=line):
                self.setUp()
                skill = self.release / "golden-skill/SKILL.md"
                self.append(skill, line)
                failures = check_rules.Check(self.root, self.release).run()
                self.assertTrue(failures, line)
                for failure in failures:
                    self.assertTrue(failure.startswith(at) and any(r in failure for r in reasons), failure)

    def test_plain_lines_build_unchanged_and_pass_the_release_check(self):
        lines = faults("Plain lines")
        self.append(self.root / SKILL, "\n".join(lines))
        self.assertTrue(build.build(self.root)["golden-skill/SKILL.md"].endswith("\n".join(lines) + "\n"))
        self.append(self.release / "golden-skill/SKILL.md", "\n".join(lines))
        self.assertEqual(check_rules.Check(self.root, self.release).run(), [])

    def test_a_tag_in_the_frontmatter_fails_both_readers(self):
        template, skill = self.root / SKILL, self.release / "golden-skill/SKILL.md"
        for path in (template, skill):
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace("Never used as a real skill.", "Follow {{rule:CORE-WORK-01}}.", 1))
        with self.assertRaisesRegex(build.tags.TagError, "SKILL.tmpl.md:3: the frontmatter holds no rule tag"):
            build.build(self.root)
        failures = check_rules.Check(self.root, self.release).run()
        self.assertEqual([f.split(": ")[0] for f in failures], ["release/golden-skill/SKILL.md:3"])

    def test_a_title_with_a_comma_builds_and_passes_the_release_check(self):
        work = self.root / "v2/rules/core/work.md"
        work.write_text(work.read_text(encoding="utf-8").replace(
            "· Report only what you verified", "· Report only what you verified, and say how"), encoding="utf-8")
        build.write(self.release, build.build(self.root))
        text = (self.release / "golden-skill/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Rules: CORE-TEST-011 (A test checks one behaviour), CORE-WORK-01 (Report only what you "
                      "verified, and say how)\n", text)
        self.assertEqual(check_rules.Check(self.root, self.release).run(), [])

    def test_the_form_itself_is_left_as_it_is(self):
        line = "Rules: {{rule:<ID>}}, {{rule:<ID>}}"
        self.append(self.root / SKILL, line)
        self.assertTrue(build.build(self.root)["golden-skill/SKILL.md"].endswith(f"\n{line}\n"))
        self.append(self.release / "golden-skill/SKILL.md", line)
        self.assertEqual(check_rules.Check(self.root, self.release).run(), [])

    def test_tag_ids_reach_like_bare_ids(self):
        """A rule cited only by a tag is copied, as one cited bare would be."""
        self.append(self.root / SKILL, "6. Time the run.\n   Rules: {{rule:CORE-WORK-02}}")
        files = build.build(self.root)
        self.assertIn("<!-- rule CORE-WORK-02 -->", files["golden-skill/SKILL.md"])


if __name__ == "__main__":
    unittest.main()
