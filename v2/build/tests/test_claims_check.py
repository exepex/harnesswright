"""Tests for the claims check script, which ships in release/, so it is loaded by path. Each case breaks one thing in
a passing claims file. Run: python3 -m unittest discover -s v2/build/tests"""

import hashlib
import importlib.util
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "v2" / "skills" / "claims-writer" / "scripts"
sys.path[:0] = [str(SCRIPTS), str(ROOT / "v2" / "build")]  # its own module, and the shipped ones it imports
SPEC = importlib.util.spec_from_file_location("claims_check", SCRIPTS / "claims_check.py")
claims_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(claims_check)
SKILL = ROOT / "release" / "claims-writer"  # the built skill: its SKILL.md is what a run hashes
claims_check.claims_standards.SKILL_DIR = SKILL
SKILL_HASH = hashlib.sha256((SKILL / "SKILL.md").read_bytes()).hexdigest()
VERSION = (ROOT / "v2" / "VERSION").read_text(encoding="utf-8").strip()
RULES_MD = """# Resolved standards

## Stack: core

### Waivers

| Rule | Reason | Until | Approved by | Status |
|---|---|---|---|---|
| CORE-ERR-01 | legacy \\| old format | 2027-03-01 | a, b | applied |
| TEAM-LOG-01 | old | 2026-01-01 | a, b | expired |

## Stack: java
"""
BLOCK = "<!-- read-back -->\nStack: {}. Rules in this text: {}. Last rule: {}.\n<!-- end read-back -->"
CORE = BLOCK.format("core", 0, "none")
JAVA = BLOCK.format("java", 1, "APP-JAVA-01 · Use records")
TEXT = ("# Rules text: claims-writer\n\n## Stack: {}\n\n### Changes to rules that reach this run\n\n{}\n\n"
        "### Decision points\n\n{}\n\n{}\n")
CORE_TEXT = TEXT.format("core", "- CORE-WORK-01 · Fresh evidence: tightened by APP-JAVA-01\n- CORE-ERR-01 · Error "
                        "format: waived until 2027-03-01: legacy", "- CORE-DP-01 · Style: `a` (from default)", CORE)
JAVA_TEXT = TEXT.format("java", "- JAVA-TEST-01 · Tests: replaced by APP-JAVA-01",
                        "- JAVA-DP-01 · Boilerplate: `records` (from acme company)", JAVA)

STORY = """---
id: S01
plan: none
covers: [AC-1, AC-2, NFR-1, NFR-2, TD-1]   # a TD and an NFR not testable here are not requirements
tests: {AC-1: [unit], AC-2: [unit, api], NFR-1: [performance]}
targets: {NFR-1: exact, NFR-2: not testable here}
waivers:
  - rule: APP-JAVA-02
    reason: the old client
    until: 2027-01-01
    approved by: a, b
---

## What

Reject a negative quantity.
"""
CLAIMS = """## Request

> Reject a negative quantity.

## Requirements

### AC-1

- **Status:** met
- **Done:** `quantity` is checked, `src/pricing.py:2`.
- **Evidence:** `python3 -m unittest` printed `OK`, exit code 0.
  The output:

```text
Ran 2 tests in 0.001s
OK
```

- **Test types:**
  - unit: `test_negative`, `tests/test_pricing.py:3`

### AC-2

- **Status:** not met
- **Done:** the API returns 500, `src/pricing.py:1-3`.
- **Evidence:** `test_api` failed, `tests/test_pricing.py:5`.
- **Test types:**
  - unit: `test_zero`,
    `tests/test_pricing.py:4`
  - api: `test_api`, `tests/test_pricing.py:5`

### NFR-1

- **Status:** not verified
- **Done:** nothing to measure here.
- **Evidence:** none in this run.
- **Test types:**
  - performance: OP-1

## Open proof items

### OP-1

- **Unproven:** NFR-1, performance.
- **Proof:** the nightly load run on staging.
- **Owner:** not named

## Standards

- **rules.md:** RULES_HASH

### Skills run

#### claims-writer

- **Source:** this run
- **Version:** VERSION
- **SKILL.md:** SKILL_HASH

```text
CORE
```

```text
JAVA
```

#### implementer

- **Source:** log
- **Version:** 0.3.1
- **SKILL.md:** unknown

### Changes applied

- CORE-WORK-01 · Fresh evidence
- CORE-ERR-01 · Error format
- JAVA-TEST-01 · Tests
- JAVA-DP-01 · Boilerplate

### Rules applied

- CORE-WORK-01 (this run)
- APP-JAVA-01 (log)

### Waivers used

- CORE-ERR-01 (this run)
- APP-JAVA-02 (this run)

## Out of scope

- Prices: another story.

## Files changed

- `src/pricing.py` (3 lines)
- `src/old.py` (deleted)

## Not verified

- NFR-1: no staging here; see `localhost:8080`.
"""
CLAIMS_PATH = ".harness/runs/r1/claims/S01.md"


CLAIMS = (CLAIMS.replace("RULES_HASH", hashlib.sha256(RULES_MD.encode()).hexdigest()).replace("VERSION", VERSION)
          .replace("SKILL_HASH", SKILL_HASH).replace("CORE\n", CORE + "\n").replace("JAVA\n", JAVA + "\n"))
OP_BLOCK = CLAIMS[CLAIMS.index("### OP-1"):CLAIMS.index("## Standards")]
FAILS = [  # (old text, new text, the fail line it must print)
    ("- **rules.md:** ", "- **rules.md:** 0", "the hash is not the SHA-256 of `.harness/runs/r1/rules.md`"),
    ("- **Version:** " + VERSION, "- **Version:** 9.9.9", "claims-writer: Version must be"),
    ("- **SKILL.md:** " + SKILL_HASH, "- **SKILL.md:** 0", "claims-writer: SKILL.md must be"),
    ("- **Source:** this run", "- **Source:** log", "claims-writer: Source must be this run"),
    ("- **Source:** log", "- **Source:** this run", "implementer: Source is `log`"),
    ("#### claims-writer", "#### claims-writer-x", "no entry for claims-writer"),
    ("SKILL.md:** " + SKILL_HASH + "\n", "SKILL.md:** " + SKILL_HASH + "\n- **Rules text:** not verified\n",
     "Rules text is `not verified` only when rules.md has a line"),
    ("Rules in this text: 1.", "Rules in this text: 2.", "not the read-back block of one of claims-writer's"),
    ("```text\n" + CORE + "\n```\n\n```text\n" + JAVA, "```text\n" + JAVA + "\n```\n\n```text\n" + CORE,
     "the read-back blocks are not in the stack order of rules.md"),
    ("- **SKILL.md:** " + SKILL_HASH + "\n\n```text\n" + CORE + "\n```\n\n```text\n" + JAVA + "\n```\n",
     "- **SKILL.md:** " + SKILL_HASH + "\n", "claims-writer quotes no read-back block"),
    ("- CORE-WORK-01 · Fresh evidence", "- CORE-WORK-02 · Fresh evidence",
     "CORE-WORK-02 · Fresh evidence is not in the changes applied"),
    ("- APP-JAVA-01 (log)", "- APP-NOPE-01 (log)", "APP-NOPE-01 is in no rule source of this run"),
    ("### Waivers used\n\n", "### Waivers used\n\nNone.\n", "Waivers used: write `None.`"),
    ("- JAVA-DP-01 · Boilerplate\n", "", "Changes applied: JAVA-DP-01 · Boilerplate is missing"),
    ("- JAVA-DP-01 · Boilerplate\n", "- CORE-DP-01 · Style\n", "CORE-DP-01 · Style is not in the changes applied"),
    ("- JAVA-DP-01 · Boilerplate\n", "- CORE-ERR-01 · Error format\n", "CORE-ERR-01 · Error format is listed twice"),
    ("- APP-JAVA-02 (this run)", "- TEAM-LOG-01 (this run)", "TEAM-LOG-01 is not in the waivers used"),
    ("- APP-JAVA-02 (this run)", "- APP-JAVA-02 (log)", "Waivers used: APP-JAVA-02 is missing"),
    ("#### implementer", "#### claims-writer", "claims-writer has a second entry under Skills run"),
    ("- **Source:** this run\n- **Version:** " + VERSION, "- **Version:** " + VERSION + "\n- **Source:** this run",
     "claims-writer must have Source, Version and SKILL.md, then Rules text"),
    ("- **Source:** this run\n", "- **Source:** this run\n- **Source:** this run\n", "Source appears twice"),
    ("- **rules.md:** ", "- rules.md: ", "it starts with one line, `- **rules.md:** <hash"),
    ("### Rules applied", "### Skills run", "Standards headings are Skills run"),
    ("```text\n" + JAVA, "```text\n" + CORE, "not the read-back block of one of claims-writer's"),
    ("- **Source:** log\n", "- **Source:** log\n- CORE-WORK-01 (this run)\n", "not a line Skills run allows"),
    ("- CORE-WORK-01 (this run)", "- CORE-WORK-0 (this run)", "CORE-WORK-0 is in no rule source of this run"),
    ("### Waivers used", "### Waivers", "Standards: the headings must be"),
    ("#### implementer\n", "#### implementer\n\n- **Owner:** x\n", "not a line the contract allows in Standards"),
    ("### AC-1\n", "### AC-1\n\nAC-1: validation added.\n", "not a line the contract allows in Requirements"),
    ("> Reject", "Reject", "not a line the contract allows in Request"),
    ("> Reject a negative quantity.\n", "", "Request: the story is not quoted"),
    ("## Request\n", "# Claims\n\n## Request\n", "the file before Request"),
    ("## Out of scope\n\n- Prices: another story.\n\n", "", "the sections must be"),
    ("## Standards", "## Extra", "not a section of the contract, or repeats one"),
    ("## Standards\n", "## Standards\n\n## Standards\n", "not a section of the contract, or repeats one"),
    (JAVA + "\n```\n", JAVA + "\n", "a code block is not closed"),
    ("### NFR-1", "### TD-1", "NFR-1: a requirement the story covers, but it has no entry"),
    ("### NFR-1", "### TD-1", "TD-1 is not a requirement the story covers"),
    ("### AC-2", "### AC-1", "AC-1 has a second entry"),
    ("## Requirements\n\n", "## Requirements\n\n- **Status:** met\n\n", "has a line before its first entry"),
    ("- **Status:** met\n", "- **Status:** done\n", "AC-1 has Status `done`"),
    ("- **Status:** met\n", "- **Status:** met\n- **Status:** not met\n", "Status appears twice"),
    ("- **Done:** nothing to measure here.\n", "", "NFR-1 must have Status, Done"),
    ("- **Done:** nothing to measure here.", "- **Done:**", "NFR-1 has no text for Done"),
    ("- **Test types:**\n  - perf", "- **Test types:** None.\n  - perf", "**Test types** holds one line"),
    ("  - api: `test_api`, `tests/test_pricing.py:5`\n", "", "AC-2 has no api test, nor the OP-n"),
    ("performance: OP-1", "performance: OP-2", "names an OP-n that Open proof items does not define"),
    ("performance: OP-1", "performance: on staging", "give the test with a `path:line` that exists"),
    ("`tests/test_pricing.py:3`", "`tests/missing_test:3`", "`tests/missing_test:3`: no such file or line"),
    ("`tests/test_pricing.py:3`", "`tests/empty.py:1`", "AC-1, unit: give the test with a `path:line`"),
    ("- **Status:** not verified", "- **Status:** met", "NFR-1 is `met`, but OP-1 stands in"),
    ("- **Owner:** not named\n", "", "OP-1 must have Unproven, Proof, Owner"),
    ("### OP-1", "### OP-2", "must be numbered OP-1, OP-2"),
    ("- `src/old.py` (deleted)", "- `tests/test_pricing.py` (deleted)", "is marked deleted, but it exists"),
    ("### OP-1\n", "None.\n\n### OP-1\n", "Open proof items: write `None.` alone"),
    ("- Prices: another story.\n", "", "Out of scope: write `None.` alone"),
    ("(3 lines)", "(4 lines)", "`src/pricing.py` has 3 lines, not 4"),
    ("- `src/pricing.py`", "- `src/gone.py`", "`src/gone.py` does not exist"),
    ("- `src/pricing.py`", "- `/src/pricing.py`", "must be a path from the project root, listed once"),
    ("(deleted)\n", "(deleted)\n- `src/old.py` (deleted)\n", "must be a path from the project root, listed once"),
    ("- `src/pricing.py` (3 lines)\n- `src/old.py` (deleted)\n", "", "Files changed lists no file"),
    ("`tests/test_pricing.py:5`", "`tests/test_pricing.py:9`", "`tests/test_pricing.py:9`: no such file or line"),
    ("`src/pricing.py:1-3`", "`src/pricing.py:1-4`", "`src/pricing.py:1-4`: no such file or line"),
]
PASSES = [  # (old text, new text): each still passes
    ("OK\n```", "OK\n## Files changed\n```"),  # a heading in a code block is output
    ("```text\nRan 2 tests in 0.001s\nOK\n```", "  ```text\nRan 2 tests `src/x.py:9`\n  ```"),  # indented block
    ("> Reject a negative quantity.", "> Reject a negative quantity, `src/x.py:9`."),  # the request is the story's
    ("see `localhost:8080`", "see `localhost:8080`, `api.example.com:443` and `http://a.b:80`"),  # not paths
    ("`tests/test_pricing.py:3`", "`app/[id]/page.py:2`"),
    ("- **Status:** met\n", "- **Status:** `met`\n"),
    ("exit code 0.\n", "exit code 0.\n  - exit code: 0\n"),  # an indented bullet under Evidence
    ("- **Status:** not verified", "- **Status:** met"),  # with the open proof item replaced below
    ("- **Version:** " + VERSION, "- **Version:** `" + VERSION + "`"),
    ("- JAVA-DP-01 · Boilerplate\n", ""),  # with the java block removed below: its changes are not wanted
]


class ClaimsCheckTest(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo)
        for path, text in (("src/pricing.py", "a\nb\nc\n"), ("app/[id]/page.py", "1\n2"), ("tests/empty.py", ""),
                           ("tests/test_pricing.py", "1\n2\n3\n4\n5\n"), (".harness/runs/r1/stories/S01.md", STORY)):
            self.write(path, text)  # brackets in a name, a last line with no newline, an empty file
        self.write(".harness/runs/r1/rules.md", RULES_MD)
        self.write(".harness/runs/r1/rules-text-claims-writer.core.md", CORE_TEXT)
        self.write(".harness/runs/r1/rules-text-claims-writer.java.md", JAVA_TEXT)
        self.write(".harness/runs/r1/log.md", "# Run log\n")
        self.claims = CLAIMS

    def write(self, path, text):
        (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / path).write_text(text, encoding="utf-8")

    def run_check(self, *args):
        self.write(CLAIMS_PATH, self.claims)
        out = io.StringIO()
        with redirect_stdout(out):
            code = claims_check.main(["--repo", str(self.repo), "--claims", CLAIMS_PATH, *args])
        return code, out.getvalue()

    def test_a_sound_file_passes_and_names_what_it_did_not_check(self):
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("not checked: Standards: entries from the run log", out)
        self.assertIn("not checked: Files changed against the change: no --base given", out)

    def test_each_fault_fails_with_its_line(self):
        for old, new, expected in FAILS:
            with self.subTest(expected=expected):
                self.assertIn(old, CLAIMS)
                self.claims = CLAIMS.replace(old, new)
                code, out = self.run_check()
                self.assertEqual(code, 1, out)
                self.assertIn(expected, out)

    def test_what_the_contract_allows_passes(self):
        for old, new in PASSES:
            with self.subTest(new=new):
                self.assertIn(old, CLAIMS)
                self.claims = CLAIMS.replace(old, new)
                if old == "- JAVA-DP-01 · Boilerplate\n":
                    self.claims = self.claims.replace("\n```text\n" + JAVA + "\n```\n", "").replace(
                        "- JAVA-TEST-01 · Tests\n", "")
                if new == "- **Status:** met":
                    self.claims = self.claims.replace(OP_BLOCK, "None.\n\n").replace("OP-1", "`src/pricing.py:1`")
                code, out = self.run_check()
                self.assertEqual(code, 0, out)

    def test_standards_follow_rules_md(self):
        self.write(".harness/runs/r1/rules.md", RULES_MD.replace("old format", "the format is not verified: legacy"))
        self.assertNotIn("Rules text", self.run_check()[1])  # a phrase in a table is not the by-reading line
        by_reading = "# Resolved standards\n\nnot verified: no profile\n"
        self.write(".harness/runs/r1/rules.md", by_reading)
        self.assertIn("claims-writer: Rules text must be not verified", self.run_check()[1])
        sha = lambda text: hashlib.sha256(text.encode()).hexdigest()  # noqa: E731
        self.claims = CLAIMS.replace(sha(RULES_MD), sha(by_reading)).replace("- CORE-ERR-01 (this run)\n", "")
        self.claims = self.claims.replace(SKILL_HASH + "\n", SKILL_HASH + "\n- **Rules text:** not verified\n")
        self.assertEqual(self.run_check()[0], 0, self.run_check()[1])  # written by reading, as step 1.3 says
        (self.repo / ".harness/runs/r1/rules.md").unlink()
        self.assertIn("rules.md` does not exist; step 1 writes it in the run folder", self.run_check()[1])

    def test_a_log_entry_needs_the_log_and_a_wrong_block_fails_alone(self):
        (self.repo / ".harness/runs/r1/log.md").unlink()
        out = self.run_check()[1]
        self.assertEqual(out.count("is written only when `.harness/runs/r1/log.md` records it"), 2, out)
        self.write(".harness/runs/r1/log.md", "# Run log\n")
        self.claims = CLAIMS.replace("Rules in this text: 1.", "Rules in this text: 2.")
        out = self.run_check()[1]
        self.assertEqual(out.count("fail: "), 1, out)  # the java changes still listed are not faults of their own
        (self.repo / ".harness/runs/r1/rules-text-claims-writer.java.md").write_bytes(b"\xff")
        self.assertEqual(self.run_check()[0], 2)  # a run file that cannot be read stops the check

    def test_the_files_the_resolver_writes(self):
        import test_runfiles  # its application: java stack, a tightening, overrides, a binding, waivers
        app = test_runfiles.RulesTextTest("test_a_rules_text_holds_what_reaches_the_run")
        app.setUp()
        self.addCleanup(app.doCleanups)
        rules_md, texts, _ = app.outputs()
        text = texts[app.repo / test_runfiles.TEXT]
        self.write(".harness/runs/r1/rules.md", rules_md)
        (self.repo / ".harness/runs/r1/rules-text-claims-writer.core.md").unlink()
        self.write(".harness/runs/r1/rules-text-claims-writer.java.md", text)
        block = text[text.index("<!-- read-back -->"):].rstrip("\n")
        changes = ("- CORE-WORK-01 · Report only what you verified\n- JAVA-TEST-01 · Title of JAVA-TEST-01\n"
                   "- COMP-ACME-CODE-01 · Title of COMP-ACME-CODE-01\n"
                   "- COMP-ACME-ERR-01 · Title of COMP-ACME-ERR-01\n"
                   "- JAVA-DP-BOILERPLATE · How boilerplate is written\n")
        standards = (f"- **rules.md:** {hashlib.sha256(rules_md.encode()).hexdigest()}\n\n### Skills run\n\n"
                     f"#### claims-writer\n\n- **Source:** this run\n- **Version:** {VERSION}\n"
                     f"- **SKILL.md:** {SKILL_HASH}\n\n```text\n{block}\n```\n\n"
                     f"### Changes applied\n\n{changes}\n### Rules applied\n\n- APP-TEST-01 (this run)\n\n"
                     "### Waivers used\n\n- COMP-ACME-ERR-01 (this run)\n- APP-JAVA-02 (this run)\n\n")
        self.claims = CLAIMS[:CLAIMS.index("- **rules.md:** ")] + standards + CLAIMS[CLAIMS.index("## Out of scope"):]
        self.assertEqual(self.run_check()[0], 0, self.run_check()[1])
        self.claims = self.claims.replace(changes, "None.\n")
        out = self.run_check()[1]
        self.assertIn("Changes applied: JAVA-DP-BOILERPLATE · How boilerplate is written is missing", out)
        self.claims = self.claims.replace("COMP-ACME-ERR-01 (this run)", "TEAM-ACME-LOG-01 (this run)")
        self.assertIn("TEAM-ACME-LOG-01 is not in the waivers used", self.run_check()[1])  # its waiver expired

    def test_the_story_frontmatter(self):
        self.write(".harness/runs/r1/stories/S01.md", STORY.replace("NFR-1, NFR-2, TD-1]", "NFR-2, TD-1]"))
        self.claims = CLAIMS.replace(CLAIMS[CLAIMS.index("### AC-1"):CLAIMS.index("## Open")], "None.\n\n")
        self.assertEqual(self.run_check()[0], 1)  # it covers AC-1 and AC-2
        self.write(".harness/runs/r1/stories/S01.md", STORY.replace("AC-1, AC-2, NFR-1, NFR-2, TD-1]", "NFR-2, TD-1]"))
        self.assertEqual(self.run_check()[0], 0)  # a story that covers no requirement
        self.write(".harness/runs/r1/stories/S01.md", "## What\n\nNo frontmatter.\n")
        self.assertIn("not checked: requirements against the story", self.run_check()[1])
        self.write(".harness/runs/r1/stories/S01.md", STORY.replace(
            "tests: {AC-1: [unit], AC-2: [unit, api], NFR-1: [performance]}", "tests:\n  AC-1: [unit]"))
        self.assertIn("flow form", self.run_check()[1])
        self.write(".harness/runs/r1/stories/S01.md", STORY.replace("[AC-1, AC-2,", "['AC-1', 'AC-2',"))
        self.assertIn("flow form", self.run_check()[1])  # a quoted ID is not the contract's form
        self.assertEqual(self.run_check("--story", "missing.md")[0], 2)

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_files_changed_equals_the_change(self):
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        self.write("src/old.py", "x\n")
        self.write("src/moved.py", "m\n")
        subprocess.run([*git, "init", "-q"], cwd=self.repo, check=True)
        subprocess.run([*git, "add", "."], cwd=self.repo, check=True)
        subprocess.run([*git, "commit", "-qm", "base"], cwd=self.repo, check=True)
        (self.repo / "src/old.py").unlink()
        subprocess.run([*git, "mv", "src/moved.py", "src/renamed.py"], cwd=self.repo, check=True)
        self.write("src/pricing.py", "a\nb\nC\n")
        self.write("src/new.py", "n\n")
        code, out = self.run_check("--base", "HEAD")
        self.assertIn("`src/new.py` changed since HEAD, but Files changed does not list it", out)
        self.assertNotIn("`.harness", out)  # the run folder is not part of the change
        self.claims = CLAIMS.replace("(deleted)\n", "(deleted)\n- `src/new.py` (1 line)\n- `src/moved.py` (deleted)\n"
                                     "- `src/renamed.py` (1 line)\n")
        self.assertEqual(self.run_check("--base", "HEAD")[0], 0)  # a rename is a deletion and a new file
        self.claims = self.claims.replace("(1 line)\n", "(1 line)\n- `tests/test_pricing.py` (5 lines)\n", 1)
        self.assertIn("did not change since HEAD", self.run_check("--base", "HEAD")[1])


if __name__ == "__main__":
    unittest.main()
