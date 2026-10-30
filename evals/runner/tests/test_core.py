"""Tests for the runner core: eval files, splitting, scoring and labels."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402

SKILL_MD = "---\nname: demo\ndescription: >\n  Writes demos.\n  Use for demos.\nlicense: MIT\n---\n# Demo\n"


def queries(should, should_not):
    return ([{"id": f"p{i:02d}", "query": "q", "should_trigger": True} for i in range(should)] +
            [{"id": f"n{i:02d}", "query": "q", "should_trigger": False} for i in range(should_not)])


class SkillFileTest(unittest.TestCase):
    def test_reads_folded_description(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "SKILL.md").write_text(SKILL_MD)
            name, description, _ = core.read_skill(folder)
        self.assertEqual((name, description), ("demo", "Writes demos. Use for demos."))

    def test_replace_description_keeps_other_fields_and_body(self):
        text = core.replace_description(SKILL_MD, 'New "quoted" text')
        lines, body = core.read_frontmatter(text)
        self.assertEqual(core._top_level_value(lines, "description"), 'New "quoted" text')
        self.assertEqual(core._top_level_value(lines, "license"), "MIT")
        self.assertEqual(body, "# Demo\n")

    def test_missing_frontmatter_is_an_error(self):
        with self.assertRaises(core.EvalError):
            core.read_frontmatter("# no frontmatter\n")

    def test_repository_skill_designer_reads(self):
        name, description, _ = core.read_skill(core.REPO_ROOT / "skills" / "skill-designer")
        self.assertEqual(name, "skill-designer")
        self.assertTrue(description.startswith("Design, source"))


class EvalFileTest(unittest.TestCase):
    def write(self, data):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(data, handle)
        handle.close()
        return handle.name

    def test_rejects_duplicate_ids(self):
        path = self.write({"skill_name": "demo", "queries": queries(1, 0) * 2})
        with self.assertRaises(core.EvalError):
            core.load_triggers(path, "demo")

    def test_rejects_wrong_skill(self):
        with self.assertRaises(core.EvalError):
            core.load_triggers(self.write({"skill_name": "other", "queries": queries(1, 1)}), "demo")

    def test_rejects_task_without_expectations(self):
        data = {"skill_name": "demo", "tasks": [{"id": 1, "name": "t", "prompt": "p", "expectations": []}]}
        with self.assertRaises(core.EvalError):
            core.load_tasks(self.write(data), "demo")

    def test_repository_evals_are_valid(self):
        folder = core.REPO_ROOT / "evals" / "skills" / "skill-designer"
        self.assertEqual(len(core.load_triggers(folder / "triggers.json", "skill-designer")), 20)
        self.assertEqual(len(core.load_tasks(folder / "tasks.json", "skill-designer")), 4)


class SplitTest(unittest.TestCase):
    def test_split_is_deterministic_and_stratified(self):
        first = core.split_queries(queries(10, 10), 0.4, seed=7)
        self.assertEqual(first, core.split_queries(queries(10, 10), 0.4, seed=7))
        train, test = first
        self.assertEqual(len(test), 8)
        self.assertEqual(sum(1 for i in test if i.startswith("p")), 4)
        self.assertFalse(set(train) & set(test))

    def test_no_holdout_keeps_everything_in_train(self):
        self.assertEqual(core.split_queries(queries(2, 1), 0)[1], [])


class ScoringTest(unittest.TestCase):
    def test_should_trigger_passes_at_half(self):
        result = core.score_query(queries(1, 0)[0], [True, False])
        self.assertEqual((result["trigger_rate"], result["passed"]), (0.5, True))

    def test_should_not_trigger_fails_at_half(self):
        self.assertFalse(core.score_query(queries(0, 1)[0], [True, False])["passed"])

    def test_failed_runs_are_not_counted_or_guessed(self):
        result = core.score_query(queries(1, 0)[0], [None, None])
        self.assertEqual((result["passed"], result["errors"], result["runs"]), (None, 2, 0))

    def test_summary_leaves_unscored_out_of_accuracy(self):
        results = [{"id": "a", "passed": True}, {"id": "b", "passed": None}, {"id": "c", "passed": False}]
        summary = core.summarise_queries(results)
        self.assertEqual((summary["accuracy"], summary["not_run"]), (0.5, 1))

    def test_task_needs_every_expectation(self):
        checks = [{"text": "script", "passed": True}, {"text": "judged", "passed": None}]
        self.assertIsNone(core.task_passed(checks, None))
        grading = {"expectations": [{"text": "judged", "passed": True}, {"text": "script", "passed": False}]}
        self.assertTrue(core.task_passed(checks, grading))
        grading["expectations"][0]["passed"] = False
        self.assertFalse(core.task_passed(checks, grading))

    def test_grader_cannot_add_or_override_script_results(self):
        checks = [{"text": "script", "passed": False}]
        grading = {"expectations": [{"text": "script", "passed": True}, {"text": "extra", "passed": True}]}
        self.assertFalse(core.task_passed(checks, grading))


def entry(**fields):
    base = {"model": "m1", "task_pass_rate": 0.9, "trigger_accuracy": 0.9, "baseline_pass_rate": 0.5,
            "lift": 0.4, "trigger_min_runs": 3, "task_min_runs": 3, "baseline_min_runs": 3}
    return {**base, **fields}


class LabelTest(unittest.TestCase):
    reference = {"task_pass_rate": 1.0, "trigger_accuracy": 0.95}

    def test_verified_within_thresholds(self):
        self.assertEqual(core.label_host(entry(), self.reference), {"label": "verified", "gaps": []})

    def test_gap_to_reference_makes_unsupported(self):
        result = core.label_host(entry(task_pass_rate=0.85, trigger_accuracy=0.95), self.reference)
        self.assertEqual(result["label"], "unsupported")
        self.assertEqual(len(result["gaps"]), 2)

    def test_missing_results_are_incomplete(self):
        for missing in ("task_pass_rate", "baseline_pass_rate"):
            self.assertEqual(core.label_host(entry(**{missing: None}), self.reference)["label"], "incomplete")

    def test_unknown_or_mixed_model_is_incomplete(self):
        for model in (None, "mixed: a, b"):
            self.assertEqual(core.label_host(entry(model=model), self.reference)["label"], "incomplete")

    def test_too_few_runs_are_inconclusive_even_when_failing(self):
        for field in ("trigger_min_runs", "task_min_runs", "baseline_min_runs"):
            result = core.label_host(entry(**{field: 1}, task_pass_rate=0.5), self.reference)
            self.assertEqual(result["label"], "inconclusive")
            self.assertIn("only 1 run(s)", result["gaps"][0])

    def test_no_lift_over_baseline_is_inconclusive(self):
        result = core.label_host(entry(task_pass_rate=1.0, baseline_pass_rate=1.0, lift=0.0), self.reference)
        self.assertEqual(result["label"], "inconclusive")
        self.assertIn("no lift", result["gaps"][0])


class TaskStatsTest(unittest.TestCase):
    def test_per_task_counts_and_spread(self):
        runs = [{"task_name": "a", "passed": True}, {"task_name": "a", "passed": False},
                {"task_name": "b", "passed": True}, {"task_name": "b", "passed": None}]
        stats = core.summarise_task_runs(runs)
        self.assertEqual(stats["tasks"]["a"], {"runs": 2, "scored": 2, "passed": 1, "pass_rate": 0.5})
        self.assertEqual(stats["min_runs_per_task"], 1)
        self.assertEqual(stats["mean"], 0.6667)
        self.assertEqual(stats["stddev"], 0.5774)


class ProvenanceTest(unittest.TestCase):
    def test_tree_hash_changes_with_content_and_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "SKILL.md").write_text(SKILL_MD)
            first = core.tree_hash(folder)
            self.assertEqual(first, core.tree_hash(folder))
            self.assertNotEqual(first, core.tree_hash(folder, {"SKILL.md": "other"}))
            Path(folder, "extra.txt").write_text("x")
            self.assertNotEqual(first, core.tree_hash(folder))

    def test_model_of_prefers_reported_and_flags_mixed(self):
        self.assertEqual(core.model_of([None, "m1", "m1"], "alias"), "m1")
        self.assertEqual(core.model_of([None], "alias"), "alias")
        self.assertIsNone(core.model_of([], None))
        self.assertEqual(core.model_of(["b", "a"], None), "mixed: a, b")

    def test_repo_commit_is_recorded(self):
        self.assertRegex(core.repo_commit() or "", r"^[0-9a-f]{40}(-dirty)?$")


class AdapterLoadingTest(unittest.TestCase):
    def test_missing_adapter_is_an_error(self):
        with self.assertRaises(core.EvalError):
            core.load_adapter("no-such-host")

    def test_shipped_adapters_have_the_interface(self):
        for host in ("claude-code", "codex"):
            self.assertEqual(core.load_adapter(host).NAME, host)


if __name__ == "__main__":
    unittest.main()
