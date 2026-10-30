"""End-to-end tests of the runner command line against a fake host that needs no network."""

import json
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402
import run_evals  # noqa: E402

FAKE_HOST = textwrap.dedent("""
    import json, os, sys
    prompt = sys.stdin.read()
    record = {"argv": sys.argv[1:], "cwd": os.getcwd(), "prompt": prompt,
              "files": sorted(os.path.join(d, f) for d, _, fs in os.walk(".") for f in fs)}
    with open(os.environ["FAKE_LOG"], "a") as log:
        log.write(json.dumps(record) + "\\n")
    if "haiku" in prompt:
        print(json.dumps({"type": "load", "skill": "demo"}))
    if "write" in prompt:
        open("result.txt", "w").write("done")
    if "refuse" in prompt:
        print(json.dumps({"type": "refused", "what": "Bash: make test"}))
    print(json.dumps({"type": "end", "text": "finished", "model": "fake-model-1"}))
""")


def fake_adapter(script, available=True, missing=None):
    def build_command(mode, workspace, model, scratch=None):
        return [sys.executable, str(script), mode] + (["--model", model] if model else [])
    return types.SimpleNamespace(
        NAME="fake", CLI=sys.executable if available else "no-such-host-cli",
        missing_requirements=lambda mode: missing if mode == "task" else None,
        permission_profile=lambda mode: {"commands": "allowed" if mode == "task" else "refused"},
        refusals=lambda events: [e["what"] for e in events if e.get("type") == "refused"],
        resolved_model=lambda events: next((e["model"] for e in events if e.get("model")), None),
        skill_dir=lambda workspace, name: Path(workspace) / ".fake" / name,
        build_command=build_command,
        environment=lambda env: env,
        parse_events=lambda out: [json.loads(line) for line in out.splitlines() if line.strip()],
        skill_triggered=lambda events, name: any(e.get("skill") == name for e in events),
        final_message=lambda events: events[-1]["text"] if events else "",
        failure=lambda events, code, timed_out, mode: None if code == 0 else f"exit code {code}")


class RunnerEndToEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.skill = self.tmp / "demo"
        self.skill.mkdir()
        (self.skill / "SKILL.md").write_text("---\nname: demo\ndescription: Writes haiku.\n---\n# Demo\n")
        self.script = self.tmp / "fake_host.py"
        self.script.write_text(FAKE_HOST)
        self.log = self.tmp / "log.jsonl"
        self.env = mock.patch.dict("os.environ", {"FAKE_LOG": str(self.log)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def run_cli(self, adapter, argv):
        with mock.patch.object(core, "load_adapter", return_value=adapter):
            return run_evals.main(argv)

    def test_triggers_scores_each_query_and_passes_model(self):
        evals = self.tmp / "triggers.json"
        evals.write_text(json.dumps({"skill_name": "demo", "queries": [
            {"id": "t1", "query": "a haiku please", "should_trigger": True},
            {"id": "t2", "query": "a limerick please", "should_trigger": False}]}))
        out = self.tmp / "triggers-result.json"
        code = self.run_cli(fake_adapter(self.script), [
            "triggers", "--skill", str(self.skill), "--host", "fake", "--evals", str(evals),
            "--out", str(out), "--runs", "2", "--model", "m1"])
        self.assertEqual(code, 0)
        result = json.loads(out.read_text())
        self.assertEqual(result["summary"]["all"]["accuracy"], 1.0)
        self.assertEqual([r["triggers"] for r in result["results"]], [2, 0])
        calls = self.calls()
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(c["argv"] == ["trigger", "--model", "m1"] for c in calls))
        self.assertTrue(all(Path(c["cwd"]).name.startswith("hw-eval-") for c in calls))
        self.assertFalse(any(Path(c["cwd"]).exists() for c in calls), "workspaces must be removed")

    def test_description_override_is_installed(self):
        evals = self.tmp / "triggers.json"
        evals.write_text(json.dumps({"skill_name": "demo", "queries": [
            {"id": "t1", "query": "haiku", "should_trigger": True}]}))
        out = self.tmp / "r.json"
        self.run_cli(fake_adapter(self.script), [
            "triggers", "--skill", str(self.skill), "--host", "fake", "--evals", str(evals),
            "--out", str(out), "--runs", "1", "--description", "Tuned text"])
        self.assertEqual(json.loads(out.read_text())["description"], "Tuned text")

    def test_missing_host_is_recorded_as_not_run(self):
        evals = self.tmp / "triggers.json"
        evals.write_text(json.dumps({"skill_name": "demo", "queries": [
            {"id": "t1", "query": "haiku", "should_trigger": True}]}))
        out = self.tmp / "r.json"
        self.run_cli(fake_adapter(self.script, available=False), [
            "triggers", "--skill", str(self.skill), "--host", "fake", "--evals", str(evals),
            "--out", str(out)])
        result = json.loads(out.read_text())
        self.assertEqual(result["status"], "not run")
        self.assertIsNone(result["results"][0]["passed"])
        self.assertIsNone(result["summary"]["all"]["accuracy"])
        self.assertFalse(self.log.exists())

    def test_tasks_save_outputs_run_checks_and_score(self):
        evals_dir = self.tmp / "evals"
        (evals_dir / "checks").mkdir(parents=True)
        (evals_dir / "files").mkdir()
        (evals_dir / "files" / "input.txt").write_text("input")
        (evals_dir / "checks" / "has_result.sh").write_text('test -f "$1/result.txt"\n')
        (evals_dir / "tasks.json").write_text(json.dumps({"skill_name": "demo", "tasks": [{
            "id": 1, "name": "write-result", "prompt": "write it", "files": ["files/input.txt"],
            "expectations": [{"text": "result exists", "check": "checks/has_result.sh"},
                             {"text": "result is good", "check": "judge"}]}]}))
        out_dir = self.tmp / "out"
        self.run_cli(fake_adapter(self.script), [
            "tasks", "--skill", str(self.skill), "--host", "fake",
            "--evals", str(evals_dir / "tasks.json"), "--out-dir", str(out_dir)])
        run_dir = out_dir / "write-result" / "with_skill" / "run-1"
        run = json.loads((run_dir / "run.json").read_text())
        self.assertEqual([c["passed"] for c in run["checks"]], [True, None])
        self.assertTrue((run_dir / "outputs" / "files" / "input.txt").exists())
        self.assertFalse((run_dir / "outputs" / ".fake" / "demo").exists(), "skill must not be graded")
        self.assertEqual((run_dir / "final-message.md").read_text(), "finished")
        self.assertEqual(self.calls()[0]["argv"], ["task"])
        self.assertEqual(run["model"], "fake-model-1")
        status = json.loads((out_dir / "status-with_skill.json").read_text())
        self.assertEqual(status["provenance"]["permission_profile"], {"commands": "allowed"})
        self.assertEqual(len(status["provenance"]["skill_sha256"]), 64)

        score = self.tmp / "score.json"
        run_evals.main(["score", "--tasks-dir", str(out_dir), "--out", str(score)])
        self.assertIsNone(json.loads(score.read_text())["task_pass_rate"], "ungraded must not pass")
        for number in (1, 2, 3):
            (run_dir.parent / f"run-{number}" / "grading.json").write_text(json.dumps(
                {"expectations": [{"text": "result is good", "passed": True, "evidence": "x"}]}))
        run_evals.main(["score", "--tasks-dir", str(out_dir), "--out", str(score)])
        scored = json.loads(score.read_text())
        self.assertEqual((scored["task_pass_rate"], scored["model"]), (1.0, "fake-model-1"))
        self.assertEqual(scored["min_runs_per_task"], 3)
        self.assertEqual(len(self.calls()), 3, "tasks run 3 times by default")

    def task_evals(self):
        evals_dir = self.tmp / "evals"
        evals_dir.mkdir(exist_ok=True)
        (evals_dir / "tasks.json").write_text(json.dumps({"skill_name": "demo", "tasks": [{
            "id": 1, "name": "write-result", "prompt": "write it",
            "expectations": [{"text": "result is good", "check": "judge"}]}]}))
        return str(evals_dir / "tasks.json")

    def run_tasks(self, adapter, out_dir, *extra):
        return self.run_cli(adapter, ["tasks", "--skill", str(self.skill), "--host", "fake",
                                      "--evals", self.task_evals(), "--out-dir", str(out_dir), *extra])

    def score(self, out_dir):
        out = self.tmp / "score.json"
        run_evals.main(["score", "--tasks-dir", str(out_dir), "--out", str(out)])
        return json.loads(out.read_text())

    def test_unavailable_host_clears_and_does_not_score_old_results(self):
        out_dir = self.tmp / "out"
        self.run_tasks(fake_adapter(self.script), out_dir, "--runs", "2")
        for run in ("run-1", "run-2"):
            (out_dir / "write-result" / "with_skill" / run / "grading.json").write_text(json.dumps(
                {"expectations": [{"text": "result is good", "passed": True}]}))
        self.assertEqual(self.score(out_dir)["task_pass_rate"], 1.0)
        self.run_tasks(fake_adapter(self.script), out_dir, "--runs", "1")
        self.assertEqual([r["run"] for r in self.score(out_dir)["runs"]], [1], "surplus runs must not count")
        self.run_tasks(fake_adapter(self.script, available=False), out_dir)
        score = self.score(out_dir)
        self.assertEqual((score["status"], score["task_pass_rate"]), ("not run", None))
        self.assertFalse((out_dir / "write-result" / "with_skill").exists())

    def test_baseline_removes_skill_inherited_from_base(self):
        base = self.tmp / "base"
        for folder in (".fake", ".agents/skills", ".claude/skills"):
            (base / folder / "demo").mkdir(parents=True)
            (base / folder / "demo" / "SKILL.md").write_text("old copy")
        (base / "keep.txt").write_text("kept")
        self.run_tasks(fake_adapter(self.script), self.tmp / "out", "--base", str(base), "--baseline")
        files = self.calls()[0]["files"]
        self.assertIn("./keep.txt", files)
        self.assertFalse([f for f in files if "SKILL.md" in f], files)

    def test_results_under_base_are_not_copied_into_workspaces(self):
        base = self.tmp / "base"
        base.mkdir()
        self.run_tasks(fake_adapter(self.script), base / "results", "--base", str(base), "--runs", "3")
        for call in self.calls():
            self.assertFalse([f for f in call["files"] if f.startswith("./results")], call["files"])

    def test_results_inside_the_eval_folder_do_not_change_the_eval_hash(self):
        out_dir = Path(self.task_evals()).parent / "results"
        self.run_tasks(fake_adapter(self.script), out_dir, "--runs", "1")
        self.run_tasks(fake_adapter(self.script), out_dir, "--runs", "1", "--baseline")
        hashes = [json.loads((out_dir / f"status-{c}.json").read_text())["provenance"]["evals_sha256"]
                  for c in ("with_skill", "without_skill")]
        self.assertEqual(hashes[0], hashes[1])

    def test_refused_action_fails_a_task_run(self):
        evals = self.task_evals()
        Path(evals).write_text(json.dumps({"skill_name": "demo", "tasks": [{
            "id": 1, "name": "write-result", "prompt": "refuse it",
            "expectations": [{"text": "result is good", "check": "judge"}]}]}))
        out_dir = self.tmp / "out"
        self.run_cli(fake_adapter(self.script), ["tasks", "--skill", str(self.skill), "--host", "fake",
                                                 "--evals", evals, "--out-dir", str(out_dir), "--runs", "1"])
        run = json.loads((out_dir / "write-result" / "with_skill" / "run-1" / "run.json").read_text())
        self.assertEqual(run["failure"], "host refused 1 action(s), first: Bash: make test")
        self.assertEqual(run["refusals"], ["Bash: make test"])

    def test_host_without_task_powers_is_not_run(self):
        out_dir = self.tmp / "out"
        self.run_tasks(fake_adapter(self.script, missing="sandbox needs bwrap"), out_dir)
        score = self.score(out_dir)
        self.assertEqual((score["status"], score["not_run_reason"]), ("not run", "sandbox needs bwrap"))
        self.assertFalse(self.log.exists())

    def write(self, name, data):
        path = self.tmp / name
        path.write_text(json.dumps(data))
        return str(path)

    def label_files(self, prefix, accuracy=1.0, not_run=0, rate=1.0, base=0.5, runs=3, model="m1", skill="s1"):
        source = {"provenance": {"skill_sha256": skill, "evals_sha256": "e1"}, "model": model}
        triggers = self.write(f"{prefix}-t.json", {**source, "summary": {"all": {
            "accuracy": accuracy, "not_run": not_run}}, "results": [{"runs": runs}]})
        score = self.write(f"{prefix}-s.json", {**source, "configuration": "with_skill",
                                                "task_pass_rate": rate, "min_runs_per_task": runs})
        baseline = self.write(f"{prefix}-b.json", {**source, "configuration": "without_skill",
                                                   "task_pass_rate": base, "min_runs_per_task": runs})
        return f"{triggers},{score},{baseline}"

    def test_label_combines_hosts(self):
        out = self.tmp / "labels.json"
        code = run_evals.main([
            "label", "--skill", "demo", "--reference", "ref", "--out", str(out),
            "--entry", "ref," + self.label_files("ref"),
            "--entry", "weak," + self.label_files("weak", accuracy=0.7),
            "--entry", "partial," + self.label_files("partial", not_run=19),
            "--entry", "few," + self.label_files("few", runs=1),
            "--entry", "nolift," + self.label_files("nolift", base=1.0),
            "--compatible", "open-host,no credentials"])
        self.assertEqual(code, 0)
        hosts = {h["host"]: h for h in json.loads(out.read_text())["hosts"]}
        self.assertEqual({h: e["label"] for h, e in hosts.items()}, {
            "ref": "verified", "weak": "unsupported", "partial": "incomplete", "few": "inconclusive",
            "nolift": "inconclusive", "open-host": "compatible"})
        self.assertEqual((hosts["ref"]["model"], hosts["ref"]["lift"]), ("m1", 0.5))

    def test_label_refuses_results_from_different_skill_versions(self):
        out = self.tmp / "labels.json"
        code = run_evals.main(["label", "--skill", "demo", "--out", str(out),
                               "--entry", "claude-code," + self.label_files("a"),
                               "--entry", "codex," + self.label_files("b", skill="s2")])
        self.assertEqual(code, 2)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
