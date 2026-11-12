"""Tests for reach.py and copyform.py. Run: python3 -m unittest discover -s v2/build/tests"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "v2" / "build"))

import copyform  # noqa: E402
import reach  # noqa: E402
import rulebook  # noqa: E402

ROLE, OTHER = "implementer", "test writer"


def rule(rule_id, applies=ROLE, kind="principle", status="active", **extra):
    parts = {"Status": [status], "Applies to": [applies], **{k: [v] for k, v in extra.items()}}
    if not rulebook.DP_ID.fullmatch(rule_id):
        parts["Kind"] = [kind]
    return rulebook.Rule(rule_id, f"Title of {rule_id}", "f.md", 1, parts)


def skill(name, roles=ROLE, areas="TEST"):
    return reach.read_skill(name, {"name": name, "metadata": {"roles": roles, "areas": areas}})


def row(name, roles, skills, rest):
    return {"Job": name, "Roles": roles.split(", "), "Skills in order": skills.split(", "), "`rest` skill": rest}


def ids(rules):
    return [r.id for r in rules]


class SizeAndSkillTest(unittest.TestCase):
    def test_size_counts_code_points(self):
        self.assertEqual(reach.size("aé😀\n"), 4)

    def test_area_of_an_id(self):
        self.assertEqual([rule(i).area for i in ("CORE-TEST-01", "JAVA-ERR-12", "CORE-DP-TEST-STACK")],
                         ["TEST", "ERR", "DP"])

    def test_good_skill(self):
        found = skill("a", f"{ROLE}, {OTHER}", "TEST, NAME")
        self.assertEqual((found.roles, found.areas, found.is_rest), ((ROLE, OTHER), ("TEST", "NAME"), False))
        self.assertTrue(skill("a", areas="rest").is_rest)

    def test_bad_skills(self):
        cases = [
            ({"name": "b", "metadata": {"roles": ROLE, "areas": "TEST"}}, "not the folder name"),
            ({"name": "a", "metadata": {"areas": "TEST"}}, "metadata.roles"),
            ({"name": "a", "metadata": {"roles": f"{ROLE}, {ROLE}", "areas": "TEST"}}, "metadata.roles"),
            ({"name": "a", "metadata": {"roles": "every role", "areas": "TEST"}}, "metadata.roles"),
            ({"name": "a", "metadata": {"roles": "Implementer", "areas": "TEST"}}, "metadata.roles"),
            ({"name": "a", "metadata": {"roles": ROLE}}, "metadata.areas"),
            ({"name": "a", "metadata": {"roles": ROLE, "areas": "TEST, TEST"}}, "metadata.areas"),
            ({"name": "a", "metadata": {"roles": ROLE, "areas": "test"}}, "metadata.areas"),
            ({"name": "a", "metadata": {"roles": ROLE, "areas": "rest, TEST"}}, "metadata.areas"),
        ]
        for frontmatter, message in cases:
            with self.subTest(frontmatter=frontmatter), self.assertRaisesRegex(reach.ReachError, message):
                reach.read_skill("a", frontmatter)


class JobsTest(unittest.TestCase):
    SKILLS = {"plan-it": skill("plan-it"), "build-it": skill("build-it", areas="rest")}
    JOBS = {"build": row("build", ROLE, "plan-it, build-it", "build-it")}

    def test_empty_roster_passes(self):
        self.assertEqual(reach.check_jobs({}, {}), {})

    def test_good_jobs(self):
        owner = reach.check_jobs(self.JOBS, self.SKILLS)
        self.assertEqual({name: r["Job"] for name, r in owner.items()}, {"plan-it": "build", "build-it": "build"})
        multi = {"x": skill("x", f"{OTHER}, {ROLE}", "rest")}
        self.assertIn("x", reach.check_jobs({"j": row("j", f"{ROLE}, {OTHER}", "x", "x")}, multi))

    def test_bad_jobs(self):
        cases = [
            (self.JOBS | {"more": row("more", ROLE, "ghost", "ghost")}, self.SKILLS, "has no template"),
            (self.JOBS | {"more": row("more", ROLE, "build-it", "build-it")}, self.SKILLS, "in two jobs"),
            (self.JOBS, self.SKILLS | {"lone": skill("lone", areas="rest")}, "in no job"),
            (self.JOBS, self.SKILLS | {"plan-it": skill("plan-it", OTHER)}, "differ from job build"),
            (self.JOBS, self.SKILLS | {"plan-it": skill("plan-it", f"{ROLE}, {OTHER}")}, "differ from job build"),
            (self.JOBS, self.SKILLS | {"build-it": skill("build-it")}, "exactly one `rest` skill.*none"),
            (self.JOBS, self.SKILLS | {"plan-it": skill("plan-it", areas="rest")}, "plan-it, build-it"),
            ({"build": row("build", ROLE, "plan-it, build-it", "plan-it")}, self.SKILLS, "exactly one `rest`"),
        ]
        for jobs, skills, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(reach.ReachError, message):
                reach.check_jobs(jobs, skills)

    def test_job_by_name(self):
        self.assertEqual(reach.job(self.JOBS, "build")["Job"], "build")
        with self.assertRaisesRegex(reach.ReachError, "unknown job 'deploy'; the roles file lists build"):
            reach.job(self.JOBS, "deploy")
        with self.assertRaisesRegex(reach.ReachError, "lists no jobs"):
            reach.job({}, "deploy")

    def test_rest_areas(self):
        rules = [rule("CORE-TEST-01"), rule("CORE-NAME-01"), rule("CORE-DOC-01", f"{OTHER}, {ROLE}"),
                 rule("CORE-SEC-01", OTHER), rule("CORE-OPS-01", status="inferred"), rule("CORE-DP-X")]
        job_row = self.JOBS["build"]
        rest = reach.areas_of(self.SKILLS["build-it"], job_row, self.SKILLS, rules)
        self.assertEqual(rest, {"NAME", "DOC"})
        self.assertEqual(reach.areas_of(self.SKILLS["plan-it"], job_row, self.SKILLS, rules), {"TEST"})


class ReachTest(unittest.TestCase):
    RULES = [
        rule("CORE-WORK-01", kind="floor"),                           # 1: floor naming the role
        rule("CORE-WORK-02", OTHER, kind="floor"),                    # floor of another role
        rule("CORE-SEC-01", f"every role, {OTHER}"),                  # 2: every role
        rule("CORE-DP-STACK"),                                        # 3: decision point naming the role
        rule("CORE-DP-OTHER", OTHER),                                 # decision point of another role
        rule("CORE-TEST-01"),                                         # 4: role and area
        rule("CORE-NAME-01"),                                         # role, area not listed
        rule("CORE-TEST-02", OTHER),                                  # area, another role
        rule("CORE-DOC-01", OTHER),                                   # 5: cited only
        rule("CORE-DOC-02", OTHER, Overrides="CORE-TEST-01"),         # 6: changes a rule that reaches
        rule("CORE-DOC-03", OTHER, Overrides="CORE-DOC-02"),          # 6, applied again
        rule("CORE-DOC-04", OTHER, Binds="CORE-DP-OTHER"),            # changes a rule that does not reach
        rule("CORE-OPS-01", "every role", status="inferred"),         # inferred never reaches
        rule("CORE-OPS-02", "every role", kind="floor", status="retired"),
    ]

    def test_the_six_items(self):
        found = reach.reach(self.RULES, [ROLE], {"TEST"}, {"CORE-DOC-01"})
        self.assertEqual(ids(found.floors), ["CORE-WORK-01"])
        self.assertEqual(ids(found.others), ["CORE-SEC-01", "CORE-DP-STACK", "CORE-TEST-01", "CORE-DOC-01",
                                             "CORE-DOC-02", "CORE-DOC-03"])
        self.assertEqual(found.cited_points, set())
        self.assertEqual(ids(found.rules), ["CORE-WORK-01"] + ids(found.others))

    def test_each_item_alone(self):
        cases = [
            ([rule("CORE-WORK-01", kind="floor")], [], set(), ["CORE-WORK-01"]),
            ([rule("CORE-SEC-01", "every role")], [], set(), ["CORE-SEC-01"]),
            ([rule("CORE-DP-STACK")], [], set(), ["CORE-DP-STACK"]),
            ([rule("CORE-TEST-01")], [], {"TEST"}, ["CORE-TEST-01"]),
            ([rule("CORE-TEST-01")], [], {"NAME"}, []),
            ([rule("CORE-TEST-01", OTHER)], [], {"TEST"}, []),
            ([rule("CORE-DOC-01", OTHER)], ["CORE-DOC-01"], set(), ["CORE-DOC-01"]),
            ([rule("CORE-DOC-01", OTHER), rule("CORE-DOC-02", OTHER, Tightens="CORE-DOC-01")], ["CORE-DOC-01"],
             set(), ["CORE-DOC-01", "CORE-DOC-02"]),
        ]
        for rules, cited, areas, expected in cases:
            with self.subTest(expected=expected, areas=areas):
                self.assertEqual(ids(reach.reach(rules, [ROLE], areas, set(cited)).rules), expected)

    def test_cited_decision_point_gets_its_copy(self):
        found = reach.reach(self.RULES, [ROLE], set(), {"CORE-DP-OTHER"})
        self.assertEqual(found.cited_points, {"CORE-DP-OTHER"})
        self.assertIn("CORE-DOC-04", ids(found.others))

    def test_multi_role_skill_gets_each_rule_once(self):
        found = reach.reach(self.RULES, [ROLE, OTHER], {"TEST"}, set())
        self.assertEqual(ids(found.floors), ["CORE-WORK-01", "CORE-WORK-02"])
        self.assertEqual(len(ids(found.rules)), len(set(ids(found.rules))))
        self.assertIn("CORE-TEST-02", ids(found.others))

    def test_bad_citations(self):
        for cited, message in [("CORE-OPS-01", "not active"), ("CORE-OPS-02", "not active"),
                               ("CORE-NONE-01", "not in the rulebook")]:
            with self.subTest(cited=cited), self.assertRaisesRegex(reach.ReachError, f"cited {cited} is {message}"):
                reach.reach(self.RULES, [ROLE], set(), {cited})


RULE_FILE = """# CORE-TEST · Tests

### CORE-TEST-03 · A test name states the scenario

- **Kind:** principle
- **Status:** active
- **Review by:** 2027-11-03
- **Applies to:** implementer
- **Rule:** Name each test after the situation
  and the result it expects.
- **Why:** A failing test should say what broke.
- **Check:** Can I tell what failed?
- **Good:**
  ```java

  void rejectsOrder() {}
  ```
- **Bad:** `testOrder2`
- **Eval:** a test named `testOrder2`
- **Exceptions:** generated tests
- **Source:** own
"""
POINT_FILE = """# CORE-DP · Decision points

### CORE-DP-TEST-STACK · Which test tools

- **Status:** active
- **Review by:** 2027-11-03
- **Question:** Which test tools?
- **Options:**
  - `language-default`: the language default
  - `junit`: JUnit 5
- **Default:** `language-default`
- **Why:** Teams choose differently.
- **Applies to:** implementer
- **Source:** own
"""
RULE_COPY = """<!-- rule CORE-TEST-03 -->
#### CORE-TEST-03 · A test name states the scenario

- **Kind:** principle
- **Rule:** Name each test after the situation
  and the result it expects.
- **Exceptions:** generated tests
- **Good:**
  ```java

  void rejectsOrder() {}
  ```
- **Bad (do not do this):** `testOrder2`
<!-- end CORE-TEST-03 -->"""
POINT_COPY = """<!-- rule CORE-DP-TEST-STACK -->
#### CORE-DP-TEST-STACK · Which test tools

- **Question:** Which test tools?
- **Options:**
  - `language-default`: the language default
  - `junit`: JUnit 5
- **Default:** `language-default`

The binding in your rules text wins; the default applies only when unbound.
<!-- end CORE-DP-TEST-STACK -->"""


class CopyFormTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        (Path(folder.name) / "test.md").write_text(RULE_FILE, encoding="utf-8")
        (Path(folder.name) / "dp.md").write_text(POINT_FILE, encoding="utf-8")
        rules = rulebook.read_layer(folder.name).rules
        self.rule, self.point = rules["CORE-TEST-03"], rules["CORE-DP-TEST-STACK"]

    def test_copy_forms_are_verbatim(self):
        self.assertEqual(copyform.copy_rule(self.rule), RULE_COPY)
        self.assertEqual(copyform.copy_point(self.point), POINT_COPY)
        del self.rule.parts["Exceptions"]
        self.assertNotIn("Exceptions", copyform.copy_rule(self.rule))

    def test_wrong_form_fails(self):
        with self.assertRaisesRegex(ValueError, "use copy_point"):
            copyform.copy_rule(self.point)
        with self.assertRaisesRegex(ValueError, "use copy_rule"):
            copyform.copy_point(self.rule)

    def test_rules_section(self):
        floor = rule("CORE-WORK-01", kind="floor", Rule="Say only what you checked.", Good="g", Bad="b")
        uncited = reach.reach([floor, self.rule, self.point], [ROLE], {"TEST"}, set())
        text = copyform.rules_section(uncited)
        self.assertEqual(text.split("\n\n")[:3], ["## Rules for this skill", "### Floors", copyform.begin(floor.id)
                                                  + f"\n#### CORE-WORK-01 · {floor.title}"])
        self.assertLess(text.index("### Other rules"), text.index(RULE_COPY))
        self.assertNotIn("CORE-DP-TEST-STACK", text)
        cited = reach.reach([floor, self.rule, self.point], [ROLE], {"TEST"}, {"CORE-DP-TEST-STACK"})
        self.assertTrue(copyform.rules_section(cited).endswith(POINT_COPY + "\n"))

    def test_read_back(self):
        self.assertEqual(copyform.read_back([self.point, self.rule]),
                         "<!-- read-back -->\nRules in this text: 2. Last rule: CORE-TEST-03 · A test name states the "
                         "scenario.\n<!-- end read-back -->\n")
        self.assertIn("Rules in this text: 0. Last rule: none.", copyform.read_back([]))


class RealRulebookTest(unittest.TestCase):
    def test_core_reaches_a_skill_designer_template_skill(self):
        layer = rulebook.read_layer(ROOT / "v2" / "rules" / "core")
        found = reach.reach(list(layer.rules.values()), ["skill designer"], {"TEMPLATE"}, set())
        reached = ids(found.rules)
        self.assertIn("CORE-WORK-01", reached)
        self.assertIn("CORE-TEMPLATE-02", reached)
        self.assertFalse(any(layer.rules[i].status != "active" for i in reached))
        text = copyform.rules_section(found)
        self.assertEqual(text.count("<!-- rule "), len(reached))
        self.assertEqual(text.count("<!-- end "), len(reached))
        self.assertLess(reach.size(text), 60000)


if __name__ == "__main__":
    unittest.main()
