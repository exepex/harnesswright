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
    print(json.dumps({"type": "end", "text": "finished"}))
""")


def fake_adapter(script, available=True):
    def build_command(mode, workspace, model):
        return [sys.executable, str(script), mode] + (["--model", model] if model else [])
    return types.SimpleNamespace(
        NAME="fake", CLI=sys.executable if available else "no-such-host-cli",
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

        score = self.tmp / "score.json"
        run_evals.main(["score", "--tasks-dir", str(out_dir), "--out", str(score)])
        self.assertIsNone(json.loads(score.read_text())["task_pass_rate"], "ungraded must not pass")
        (run_dir / "grading.json").write_text(json.dumps(
            {"expectations": [{"text": "result is good", "passed": True, "evidence": "x"}]}))
        run_evals.main(["score", "--tasks-dir", str(out_dir), "--out", str(score)])
        self.assertEqual(json.loads(score.read_text())["task_pass_rate"], 1.0)

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

    def test_label_combines_hosts(self):
        def write(name, data):
            path = self.tmp / name
            path.write_text(json.dumps(data))
            return str(path)
        good = write("t1.json", {"summary": {"all": {"accuracy": 0.95, "not_run": 0}}})
        weak = write("t2.json", {"summary": {"all": {"accuracy": 0.7, "not_run": 0}}})
        partial = write("t3.json", {"summary": {"all": {"accuracy": 1.0, "not_run": 19}}})
        score = write("s.json", {"task_pass_rate": 1.0})
        out = self.tmp / "labels.json"
        run_evals.main(["label", "--skill", "demo", "--reference", "ref",
                        "--entry", f"ref,default,{good},{score}", "--entry", f"other,m2,{weak},{score}",
                        "--entry", f"third,m3,{partial},{score}",
                        "--compatible", "open-host,no credentials", "--out", str(out)])
        labels = {h["host"]: h["label"] for h in json.loads(out.read_text())["hosts"]}
        self.assertEqual(labels, {"ref": "verified", "other": "unsupported", "third": "incomplete",
                                  "open-host": "compatible"})


if __name__ == "__main__":
    unittest.main()
