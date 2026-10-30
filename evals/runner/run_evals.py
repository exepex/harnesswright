#!/usr/bin/env python3
"""Run a skill's trigger and task evals on one host through its adapter.

Usage (from the repository root):
  python3 evals/runner/run_evals.py triggers --skill skills/NAME --host HOST --out FILE
  python3 evals/runner/run_evals.py tasks --skill skills/NAME --host HOST --out-dir DIR
  python3 evals/runner/run_evals.py score --tasks-dir DIR --out FILE
  python3 evals/runner/run_evals.py label --skill NAME --reference HOST --entry ... --out FILE

Every result records what produced it (provenance): the runner commit, host version, model, permission
profile, and hashes of the skill and the eval files.

See evals/runner/README.md for every option and the result formats.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402


def cmd_triggers(args):
    adapter = core.load_adapter(args.host)
    name, description, text = core.read_skill(args.skill)
    evals_file = args.evals or core.REPO_ROOT / "evals" / "skills" / name / "triggers.json"
    queries = core.load_triggers(evals_file, name)
    if args.description:
        description, text = args.description, core.replace_description(text, args.description)
    reason = core.host_available(adapter, "trigger")
    if reason:
        core.warn(f"{args.host}: not run: {reason}")
    results, models = [], []
    for query in sorted(queries, key=lambda q: q["id"]):
        outcomes = []
        for _ in range(args.runs if not reason else 0):
            workspace = core.make_workspace(adapter, args.skill, name, text)
            try:
                run = core.run_host(adapter, workspace, query["query"], "trigger", args.model, args.timeout)
            finally:
                shutil.rmtree(workspace, ignore_errors=True)
            models.append(run["model"])
            if run["failure"]:
                core.warn(f"{query['id']}: run failed: {run['failure']}")
                outcomes.append(None)
            else:
                outcomes.append(adapter.skill_triggered(run["events"], name))
        results.append(core.score_query(query, outcomes, args.threshold))
    train, test = core.split_queries(queries, args.holdout, args.seed)
    for result in results:
        result["split"] = "test" if result["id"] in test else "train"
    output = {"skill_name": name, "host": args.host, "model": core.model_of(models, args.model),
              "provenance": core.provenance(adapter, "trigger", args.model, args.skill, text, evals_file),
              "description": description, "runs_per_query": args.runs, "threshold": args.threshold,
              "status": "not run" if reason else "run", "not_run_reason": reason,
              "results": results,
              "summary": {"all": core.summarise_queries(results),
                          "train": core.summarise_queries(results, set(train)),
                          "test": core.summarise_queries(results, set(test))}}
    core.write_json(args.out, output)
    print(json.dumps(output["summary"]["all"]))
    return 0


def run_checks(task, evals_dir, outputs, timeout):
    checks = []
    for expectation in task["expectations"]:
        entry = {"text": expectation["text"], "check": expectation["check"], "passed": None}
        if expectation["check"] != "judge":
            script = (evals_dir / expectation["check"]).resolve()
            runner = [sys.executable] if script.suffix == ".py" else ["sh"]
            try:
                done = subprocess.run(runner + [str(script), str(outputs)], capture_output=True,
                                      text=True, timeout=timeout)
                entry.update(passed=done.returncode == 0, exit_code=done.returncode,
                             output=(done.stdout + done.stderr)[-2000:])
            except subprocess.TimeoutExpired:
                entry.update(passed=False, exit_code=None, output="check timed out")
        checks.append(entry)
    return checks


def cmd_tasks(args):
    adapter = core.load_adapter(args.host)
    name, _, text = core.read_skill(args.skill)
    evals_dir = Path(args.evals).parent if args.evals else core.REPO_ROOT / "evals" / "skills" / name
    tasks_file = args.evals or evals_dir / "tasks.json"
    tasks = core.load_tasks(tasks_file, name)
    config = "without_skill" if args.baseline else "with_skill"
    reason = core.host_available(adapter, "task")
    if reason:
        core.warn(f"{args.host}: not run: {reason}")
    out_dir = Path(args.out_dir)
    # Results of an earlier invocation must never be scored as this one's.
    for task in tasks:
        shutil.rmtree(out_dir / task["name"] / config, ignore_errors=True)
    core.write_json(out_dir / f"status-{config}.json", {
        "host": args.host, "status": "not run" if reason else "run", "not_run_reason": reason,
        "provenance": {**core.provenance(adapter, "task", args.model, args.skill, text, tasks_file, out_dir),
                       "base_sha256": core.tree_hash(args.base, exclude=[out_dir]) if args.base else None},
        "runs": [{"task_name": t["name"], "run": n} for t in sorted(tasks, key=lambda t: t["id"])
                 for n in range(1, (args.runs if not reason else 0) + 1)]})
    for task in sorted(tasks, key=lambda t: t["id"]):
        for number in range(1, (args.runs if not reason else 0) + 1):
            run_dir = out_dir / task["name"] / config / f"run-{number}"
            # Earlier results under --base must not leak into a later workspace.
            workspace = core.make_workspace(adapter, None if args.baseline else args.skill, name,
                                            text, base=args.base, exclude=[out_dir])
            for relative in task.get("files", []):
                target = workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(evals_dir / relative, target)
            try:
                run = core.run_host(adapter, workspace, task["prompt"], "task", args.model, args.timeout)
                if not args.baseline:
                    shutil.rmtree(adapter.skill_dir(workspace, name), ignore_errors=True)
                shutil.copytree(workspace, run_dir / "outputs")
            finally:
                shutil.rmtree(workspace, ignore_errors=True)
            (run_dir / "transcript.jsonl").write_text(run["stdout"], encoding="utf-8")
            (run_dir / "final-message.md").write_text(adapter.final_message(run["events"]),
                                                      encoding="utf-8")
            checks = [] if run["failure"] else run_checks(task, evals_dir, run_dir / "outputs",
                                                          args.timeout)
            core.write_json(run_dir / "run.json", {
                "skill_name": name, "host": args.host, "model": core.model_of([run["model"]], args.model),
                "task_id": task["id"], "task_name": task["name"], "configuration": config,
                "run": number, "failure": run["failure"], "returncode": run["returncode"],
                "refusals": run["refusals"], "checks": checks})
            core.warn(f"{task['name']} run {number}: {run['failure'] or 'done'}")
    return 0


def cmd_score(args):
    tasks_dir = Path(args.tasks_dir)
    status_file = tasks_dir / f"status-{args.configuration}.json"
    if not status_file.exists():
        raise core.EvalError(f"{status_file} not found; run the tasks command first")
    status = json.loads(status_file.read_text(encoding="utf-8"))
    runs, models = [], []
    # Score exactly the runs the latest invocation made, never leftovers.
    for expected in status["runs"]:
        run_dir = tasks_dir / expected["task_name"] / args.configuration / f"run-{expected['run']}"
        run_file, grading_file = run_dir / "run.json", run_dir / "grading.json"
        run = json.loads(run_file.read_text(encoding="utf-8")) if run_file.exists() else None
        grading = json.loads(grading_file.read_text(encoding="utf-8")) if grading_file.exists() else None
        failure = "run.json missing" if run is None else run["failure"]
        models.append(run and run.get("model"))
        passed = None if failure else core.task_passed(run["checks"], grading)
        runs.append({**expected, "failure": failure, "passed": passed})
    scored = [r for r in runs if r["passed"] is not None]
    complete = status["status"] == "run" and scored and len(scored) == len(runs)
    rate = round(sum(r["passed"] for r in scored) / len(scored), 4) if complete else None
    output = {"configuration": args.configuration, "status": status["status"],
              "not_run_reason": status["not_run_reason"], "provenance": status.get("provenance"),
              "model": core.model_of(models, (status.get("provenance") or {}).get("requested_model")),
              "runs": runs, "task_pass_rate": rate, "ungraded_or_failed": len(runs) - len(scored),
              **core.summarise_task_runs(runs)}
    core.write_json(args.out, output)
    print(json.dumps({"task_pass_rate": rate, "ungraded_or_failed": output["ungraded_or_failed"]}))
    return 0


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _same(values, what, where):
    found = {v for v in values if v is not None}
    if len(found) > 1:
        raise core.EvalError(f"{where}: results come from different {what}: {', '.join(sorted(found))}")
    return found.pop() if found else None


def cmd_label(args):
    entries, skill_hashes = [], []
    for raw in args.entry:
        parts = raw.split(",")
        if len(parts) != 4:
            raise core.EvalError(f"--entry needs HOST,TRIGGERS,TASK_SCORE,BASELINE_SCORE: {raw}")
        host, triggers, score, baseline = parts[0], _read(parts[1]), _read(parts[2]), _read(parts[3])
        if score.get("configuration") != "with_skill" or baseline.get("configuration") != "without_skill":
            raise core.EvalError(f"{host}: TASK_SCORE must be with_skill and BASELINE_SCORE without_skill")
        sources = [(f.get("provenance") or {}) for f in (triggers, score, baseline)]
        skill_hashes.append(_same([p.get("skill_sha256") for p in sources], "skill versions", host))
        _same([p.get("evals_sha256") for p in sources[1:]], "task eval files", host)
        if len({p.get("base_sha256") for p in sources[1:]}) > 1:
            raise core.EvalError(f"{host}: with- and without-skill task runs used different --base contents")
        models = [f.get("model") for f in (triggers, score, baseline)]
        model = models[0] if len(set(models)) == 1 else "mixed: " + ", ".join(sorted(map(str, set(models))))
        rate, base = score["task_pass_rate"], baseline["task_pass_rate"]
        entries.append({"host": host, "model": model,
                        "trigger_accuracy": triggers["summary"]["all"]["accuracy"],
                        "trigger_not_run": triggers["summary"]["all"]["not_run"],
                        "trigger_min_runs": min((r["runs"] for r in triggers["results"]), default=0),
                        "task_pass_rate": rate, "task_min_runs": score.get("min_runs_per_task", 0),
                        "baseline_pass_rate": base, "baseline_min_runs": baseline.get("min_runs_per_task", 0),
                        "lift": round(rate - base, 4) if None not in (rate, base) else None,
                        "provenance": {"triggers": sources[0], "tasks": sources[1], "baseline": sources[2]}})
    _same(skill_hashes, "skill versions", "hosts")
    reference = next((e for e in entries if e["host"] == args.reference), None)
    if reference is None:
        raise core.EvalError(f"no entry for the reference host '{args.reference}'")
    for entry in entries:
        entry.update(core.label_host(entry, reference))
    for raw in args.compatible:
        host, reason = (raw.split(",", 1) + ["evals not run"])[:2]
        entries.append({"host": host, "model": "any", "label": "compatible", "gaps": [], "reason": reason})
    output = {"skill_name": args.skill, "reference_host": args.reference,
              "thresholds": core.THRESHOLDS, "hosts": entries}
    core.write_json(args.out, output)
    print(json.dumps([{e["host"]: e["label"]} for e in entries]))
    return 0


def parser():
    top = argparse.ArgumentParser(description="Run harnesswright skill evals on one host.")
    sub = top.add_subparsers(dest="command", required=True)
    for name in ("triggers", "tasks"):
        p = sub.add_parser(name)
        p.add_argument("--skill", required=True, type=Path, help="skill folder")
        p.add_argument("--host", required=True, help="adapter name under adapters/")
        p.add_argument("--evals", type=Path, help="eval file (default: evals/skills/NAME/...)")
        p.add_argument("--model", help="model for the host (default: the host's own)")
        p.add_argument("--timeout", type=int, default=120 if name == "triggers" else 900)
    trig = sub.choices["triggers"]
    trig.add_argument("--out", required=True, type=Path)
    trig.add_argument("--runs", type=int, default=3)
    trig.add_argument("--threshold", type=float, default=0.5)
    trig.add_argument("--holdout", type=float, default=0.0)
    trig.add_argument("--seed", type=int, default=42)
    trig.add_argument("--description", help="test this description instead of the skill's own")
    trig.set_defaults(func=cmd_triggers)
    task = sub.choices["tasks"]
    task.add_argument("--out-dir", required=True, type=Path)
    task.add_argument("--runs", type=int, default=core.THRESHOLDS["min_runs"])
    task.add_argument("--base", type=Path, help="folder copied into each workspace first")
    task.add_argument("--baseline", action="store_true", help="run without the skill")
    task.set_defaults(func=cmd_tasks)
    score = sub.add_parser("score")
    score.add_argument("--tasks-dir", required=True, type=Path)
    score.add_argument("--configuration", default="with_skill")
    score.add_argument("--out", required=True, type=Path)
    score.set_defaults(func=cmd_score)
    label = sub.add_parser("label")
    label.add_argument("--skill", required=True)
    label.add_argument("--reference", default="claude-code")
    label.add_argument("--entry", action="append", default=[],
                       help="HOST,TRIGGERS_RESULT,TASK_SCORE,BASELINE_SCORE (repeatable)")
    label.add_argument("--compatible", action="append", default=[], help="HOST[,REASON] not run")
    label.add_argument("--out", required=True, type=Path)
    label.set_defaults(func=cmd_label)
    return top


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except core.EvalError as error:
        core.warn(f"error: {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
