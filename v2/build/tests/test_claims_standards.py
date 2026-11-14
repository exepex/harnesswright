"""Tests for the Standards checks of the claims check (claims_standards.py), on the run folder and passing claims
file of test_claims_check. Each case breaks one thing. Run: python3 -m unittest discover -s v2/build/tests"""

import hashlib
import unittest

from test_claims_check import CLAIMS, CORE, JAVA, RULES_MD, SKILL_HASH, VERSION, Run  # puts the scripts on sys.path

SHA = lambda text: hashlib.sha256(text.encode()).hexdigest()  # noqa: E731
FAILS = [  # (old text, new text, the fail line it must print)
    ("### Waivers used\n\n- CORE-ERR-01 (this run)\n- APP-JAVA-02 (this run)\n- JAVA-LOG-01 (this run)\n",
     "### Waivers used\n", "Waivers used: write `None.` alone"),  # a list with neither a line nor `None.`
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
    ("- JAVA-DP-01 · Boilerplate\n", "- JAVA-TEST-01 · Tests\n", "JAVA-TEST-01 · Tests is listed twice"),
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
    ("- CORE-WORK-01 (this run)", "- WORK-01 (this run)", "WORK-01 is in no rule source of this run"),
    ("- CORE-WORK-01 (this run)", "- CORE-WORK (this run)", "CORE-WORK is in no rule source of this run"),
    ("- APP-JAVA-01 (log)", "```text\nx\n```", "Rules applied: write `None.` alone"),
    ("### Waivers used", "### Waivers", "Standards: the headings must be"),
    ("#### implementer\n", "#### implementer\n\n- **Owner:** x\n", "not a line the contract allows in Standards"),
]
PASSES = [  # (old text, new text, ...): each still passes
    ("- **rules.md:** " + SHA(RULES_MD), "- **rules.md:** `" + SHA(RULES_MD) + "`"),
    ("- **Version:** " + VERSION, "- **Version:** `" + VERSION + "`"),
    ("\n```text\n" + JAVA + "\n```\n", "", "- JAVA-TEST-01 · Tests\n", "", "- JAVA-DP-01 · Boilerplate\n", "",
     "- JAVA-LOG-01 (this run)\n", ""),
    ("```text\n" + CORE + "\n```\n\n", "", "- CORE-WORK-01 · Fresh evidence\n", "", "- CORE-ERR-01 (this run)\n", "",
     "- CORE-ERR-01 · Error format: `json`\n", ""),  # a stack not quoted: its changes and waivers are not wanted
]


class StandardsTest(Run, unittest.TestCase):
    def test_each_fault_fails_with_its_line(self):
        self.assert_fails(FAILS)

    def test_what_the_contract_allows_passes(self):
        self.assert_passes(PASSES)

    def test_standards_follow_rules_md(self):
        self.write(".harness/runs/r1/rules.md", RULES_MD.replace("old format", "the format is not verified: legacy"))
        self.assertNotIn("Rules text", self.run_check()[1])  # a phrase in a table is not the by-reading line
        by_reading = "# Resolved standards\n\nnot verified: no profile\n"
        self.write(".harness/runs/r1/rules.md", by_reading)
        self.assertIn("claims-writer: Rules text must be not verified", self.run_check()[1])
        self.claims = CLAIMS.replace(SHA(RULES_MD), SHA(by_reading)).replace("- CORE-ERR-01 (this run)\n", "").replace(
            "- JAVA-LOG-01 (this run)\n", "")  # rules.md waives nothing now
        self.claims = self.claims.replace(SKILL_HASH + "\n", SKILL_HASH + "\n- **Rules text:** not verified\n")
        self.assertEqual(self.run_check()[0], 0, self.run_check()[1])  # written by reading, as step 1.3 says
        (self.repo / ".harness/runs/r1/rules.md").unlink()
        self.assertIn("rules.md` does not exist; step 1 writes it in the run folder", self.run_check()[1])

    def test_a_log_entry_needs_the_log_and_a_wrong_block_fails_alone(self):
        self.claims = CLAIMS.replace("Rules in this text: 1.", "Rules in this text: 2.")
        out = self.run_check()[1]
        self.assertEqual(out.count("fail: "), 1, out)  # the java changes still listed are not faults of their own
        (self.repo / ".harness/runs/r1/log.md").unlink()
        out = self.run_check()[1]
        self.assertEqual(out.count("is written only when `.harness/runs/r1/log.md` records it"), 2, out)
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
        self.write(".harness/runs/r1/rules-text-claims-writer.java.md", text)  # core's text is there, not quoted
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


if __name__ == "__main__":
    unittest.main()
