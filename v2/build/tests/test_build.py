"""Tests for build.py. Run: python3 -m unittest discover -s v2/build/tests"""

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "demo-skill"
sys.path.insert(0, str(ROOT / "v2" / "build"))

import build  # noqa: E402
import rulebook  # noqa: E402

JOB_ROW = "| demo | skill designer | demo-skill | demo-skill |\n"


class BuildTest(unittest.TestCase):
    """Builds a temporary root: the real CORE layer and roles file, plus one job row and the demo skill."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        shutil.copytree(ROOT / "v2" / "rules" / "core", self.root / "v2" / "rules" / "core")
        (self.root / "v2" / "VERSION").write_text("0.1.0\n", encoding="utf-8")
        roles = (ROOT / "v2" / "roles.md").read_text(encoding="utf-8")
        (self.root / "v2" / "roles.md").write_text(roles + JOB_ROW, encoding="utf-8")
        self.skill = self.root / "v2" / "skills" / "demo-skill"
        shutil.copytree(FIXTURE, self.skill)
        self.core = rulebook.read_layer(ROOT / "v2" / "rules" / "core").rules

    def skill_md(self):
        return build.build(self.root)["demo-skill/SKILL.md"]

    def test_building_twice_gives_the_same_bytes(self):
        outs = [self.root / "out1", self.root / "out2"]
        for seed, out in zip("12", outs):  # separate processes with different hash seeds, so set order differs
            command = [sys.executable, str(ROOT / "v2" / "build" / "build.py"), "--root", str(self.root), "--out",
                       str(out)]
            subprocess.run(command, check=True, env={**os.environ, "PYTHONHASHSEED": seed})
        trees = [{p.relative_to(o).as_posix(): p.read_bytes() for p in o.rglob("*") if p.is_file()} for o in outs]
        self.assertEqual(trees[0], trees[1])
        self.assertEqual(sorted(trees[0]), ["demo-skill/SKILL.md", "demo-skill/references/guide.md",
                                            "demo-skill/scripts/copyform.py", "demo-skill/scripts/helper.py",
                                            "demo-skill/scripts/reach.py", "demo-skill/scripts/rulebook.py",
                                            "manifest.json"])

    def test_skill_md_layout(self):
        lines = self.skill_md().split("\n")
        end = lines.index("---", 1)
        self.assertEqual(lines[:6], ["---", "name: demo-skill", lines[2], "metadata:", "  roles: skill designer",
                                     "  areas: rest"])
        self.assertEqual(lines[end - 1:end + 6], [
            "license: Apache-2.0", "---",
            "<!-- Generated from v2/skills/demo-skill/SKILL.tmpl.md at version 0.1.0. Do not edit. -->",
            "", "# Demo skill", "", "## Rules for this skill"])
        self.assertEqual(lines[-4:], [
            "1. Read the rules text first, as CORE-TEMPLATE-04 (A skill's first step reads its rules text) asks.",
            "2. Report only what you checked (CORE-WORK-01 (Report only what you verified)).",
            "3. Follow [the guide](references/guide.md).", ""])
        self.assertNotIn("\n\n\n", "\n".join(lines))

    def test_template_without_a_title(self):
        template = self.skill / "SKILL.tmpl.md"
        template.write_text(template.read_text(encoding="utf-8").replace("# Demo skill", "## Steps"))
        lines = self.skill_md().split("\n")
        start = lines.index("## Rules for this skill")
        self.assertEqual(lines[start - 2:start], ["<!-- Generated from v2/skills/demo-skill/SKILL.tmpl.md at version "
                                                  "0.1.0. Do not edit. -->", ""])
        self.assertGreater(lines.index("## Steps"), start)

    def test_names_that_hold_an_id_are_not_citations(self):
        guide = self.skill / "references" / "guide.md"
        guide.write_text("See `xCORE-WORK-02` and `CORE-WORK-03-old.md`.\n", encoding="utf-8")
        files = build.build(self.root)
        self.assertTrue(files["demo-skill/references/guide.md"].endswith("See `xCORE-WORK-02` and "
                                                                         "`CORE-WORK-03-old.md`.\n"))

    def add_point(self, role):
        """Add the decision point of test_reach.py to the temporary CORE layer, applying to role."""
        point = (Path(__file__).resolve().parent / "test_reach.py").read_text(encoding="utf-8")
        start = point.index("### CORE-DP-TEST-STACK")
        text = point[start:point.index('"""', start)].replace("implementer", role)
        (self.root / "v2" / "rules" / "core" / "dp.md").write_text("# CORE-DP · Decision points\n\n" + text)

    def test_decision_points_are_copied_only_when_cited(self):
        self.add_point("skill designer")
        self.assertNotIn("CORE-DP-TEST-STACK", json.loads(build.build(self.root)["manifest.json"])["skills"]
                         ["demo-skill"]["copied-ids"])
        template = self.skill / "SKILL.tmpl.md"
        template.write_text(template.read_text(encoding="utf-8") + "4. Pick tools as CORE-DP-TEST-STACK says.\n")
        files = build.build(self.root)
        self.assertIn("CORE-DP-TEST-STACK", json.loads(files["manifest.json"])["skills"]["demo-skill"]["copied-ids"])
        self.assertIn("<!-- rule CORE-DP-TEST-STACK -->", files["demo-skill/SKILL.md"])

    def test_the_frontmatter_cites_nothing(self):
        self.add_point("implementer")
        template = self.skill / "SKILL.tmpl.md"
        template.write_text(template.read_text(encoding="utf-8").replace("tests.", "tests, CORE-DP-TEST-STACK."))
        files = build.build(self.root)
        self.assertNotIn("CORE-DP-TEST-STACK", json.loads(files["manifest.json"])["skills"]["demo-skill"]["copied-ids"])
        self.assertIn("build tests, CORE-DP-TEST-STACK.\n", files["demo-skill/SKILL.md"])

    def test_copied_rules_and_metadata(self):
        files = build.build(self.root)
        text = files["demo-skill/SKILL.md"]
        data, body_start = self.frontmatter(text)
        entry = json.loads(files["manifest.json"])["skills"]["demo-skill"]
        meta = data["metadata"]
        copied = entry["copied-ids"]
        self.assertEqual(meta["copied-ids"], ", ".join(copied))
        for rule_id in ("CORE-WORK-01", "CORE-TEMPLATE-01", "CORE-TEMPLATE-04"):
            self.assertIn(rule_id, copied)
            self.assertEqual(text.count(f"<!-- rule {rule_id} -->"), 1)
        self.assertEqual(len(copied), text.count("<!-- rule "))
        self.assertTrue(all(self.core[i].status == "active" for i in copied))
        self.assertEqual(entry["areas"], ["CATALOG", "SKILL", "TEMPLATE"])
        body = "\n".join(text.split("\n")[body_start:])
        self.assertEqual(meta["content-hash"], hashlib.sha256(body.encode("utf-8")).hexdigest())
        self.assertEqual(entry["content-hash"], meta["content-hash"])
        floors = [i for i in copied if self.core[i].kind == "floor"]
        floor_text = "\n\n".join(build.copyform.copy_rule(self.core[i]) for i in floors)
        self.assertEqual((entry["size-floors"], entry["size-rest"]), (len(floor_text), len(body) - len(floor_text)))
        self.assertEqual((meta["size-floors"], meta["rulebook-version"]), (str(len(floor_text)), "0.1.0"))
        self.assertEqual(entry["roles"], ["skill designer"])

    def frontmatter(self, text):
        path = self.root / "probe.md"
        path.write_text(text, encoding="utf-8")
        return rulebook.read_frontmatter(path)

    def test_other_files(self):
        files = build.build(self.root)
        self.assertEqual(files["demo-skill/references/guide.md"],
                         "<!-- Generated from v2/skills/demo-skill/references/guide.md at version 0.1.0. Do not edit."
                         " -->\n\nWrite the template as CORE-TEMPLATE-01 (A template cites rules by ID and never "
                         "writes their text) asks.\n")
        self.assertEqual(files["demo-skill/scripts/helper.py"], (FIXTURE / "scripts" / "helper.py").read_bytes())
        for module in build.SHIPPED:
            self.assertEqual(files[f"demo-skill/scripts/{module}"], (ROOT / "v2" / "build" / module).read_bytes())

    def test_empty_roster(self):
        shutil.rmtree(self.skill)
        roles = (ROOT / "v2" / "roles.md").read_text(encoding="utf-8")
        (self.root / "v2" / "roles.md").write_text(roles, encoding="utf-8")
        self.assertEqual(build.build(self.root), {"manifest.json": '{\n  "rulebook-version": "0.1.0",\n'
                                                                   '  "skills": {}\n}\n'})

    def test_failures(self):
        original = (FIXTURE / "SKILL.tmpl.md").read_text(encoding="utf-8")

        def template():
            return self.skill / "SKILL.tmpl.md"
        cases = [
            (lambda: template().write_text(original + "4. See CORE-NONE-01.\n"), "cites CORE-NONE-01, which is not"),
            (lambda: (self.skill / "references" / "guide.md").write_text("CORE-NONE-02\n"), "guide.md: cites CORE"),
            (lambda: template().write_text(original.replace("rest\n", "rest\n  copied-ids: x\n")),
             "metadata.copied-ids is written by the build"),
            (lambda: template().rename(self.skill / "OTHER.md"), "has no SKILL.tmpl.md"),
            (lambda: (self.skill / "SKILL.md").write_text("x\n"), "demo-skill/SKILL.md: a skill folder holds only"),
            (lambda: (self.skill / "evals.json").write_text("{}\n"), "demo-skill/evals.json: a skill folder"),
            (lambda: (self.skill / "scripts" / "reach.py").write_text("\n"), "has the name of a shipped module"),
            (lambda: (self.root / "v2" / "VERSION").write_text("v1\n"), "must hold one version line"),
            (lambda: (self.root / "v2" / "VERSION").write_text("0.1.0\n0.2.0\n"), "must hold one version line"),
            (lambda: shutil.copytree(FIXTURE, self.root / "v2" / "skills" / "spare-skill"), "not the folder name"),
            (lambda: template().write_text(original + "4. Use CORE-SKILL-02.\n"), "CORE-SKILL-02 is not active"),
        ]
        for change, message in cases:
            with self.subTest(message=message):
                self.setUp()
                change()
                with self.assertRaisesRegex(rulebook.RulebookError, message):
                    build.build(self.root)
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    self.assertEqual(build.main(["--root", str(self.root), "--out", str(self.root / "o")]), 1)
                self.assertIn("build failed:", stderr.getvalue())
                self.assertFalse((self.root / "o").exists())

    def test_write_removes_stale_files_only_under_out(self):
        out = self.root / "release"
        (out / "old-skill" / "scripts").mkdir(parents=True)
        (out / "old-skill" / "scripts" / "x.py").write_text("\n")
        (out / ".gitkeep").write_text("")
        build.write(out, {"a/b.md": "text\n", "c.bin": b"\x00"})
        found = sorted(p.relative_to(out).as_posix() for p in out.rglob("*"))
        self.assertEqual(found, [".gitkeep", "a", "a/b.md", "c.bin"])
        self.assertEqual((out / "c.bin").read_bytes(), b"\x00")


if __name__ == "__main__":
    unittest.main()
