"""Host-neutral eval runner core: eval files, workspaces, host runs and scoring.

Python 3 standard library only. The runner makes no network calls of its own; the host
command it starts does. Everything here is deterministic for the same inputs and host output.
"""

import hashlib
import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS_DIR = REPO_ROOT / "adapters"
ADAPTER_FUNCTIONS = ("skill_dir", "build_command", "environment", "parse_events", "skill_triggered",
                     "final_message", "failure", "missing_requirements", "permission_profile",
                     "refusals", "resolved_model")
# min_runs follows skill-creator's benchmark (runs_per_configuration 3); min_lift is the least gain over
# the baseline (with skill minus without) that shows the skill does something.
THRESHOLDS = {"task_pass_rate": 0.9, "max_gap": 0.10, "trigger_accuracy": 0.9, "min_runs": 3,
              "min_lift": 0.0}
# Project folders where known hosts discover skills. A copied base folder may hold the skill under test
# in any of them, which would leak it into a baseline run or mix it with the installed copy.
SKILL_FOLDERS = (".claude/skills", ".agents/skills", ".opencode/skills", ".goose/skills")


class EvalError(Exception):
    """An eval file, skill or adapter is not usable."""


# ---- adapters ---------------------------------------------------------------

def load_adapter(host, adapters_dir=ADAPTERS_DIR):
    """Load adapters/<host>/adapter.py and check it has the whole interface."""
    path = Path(adapters_dir) / host / "adapter.py"
    if not path.is_file():
        raise EvalError(f"no adapter for host '{host}' at {path}")
    spec = importlib.util.spec_from_file_location(f"hw_adapter_{host.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    missing = [name for name in ("NAME", "CLI") + ADAPTER_FUNCTIONS if not hasattr(module, name)]
    if missing:
        raise EvalError(f"adapter '{host}' lacks: {', '.join(missing)}")
    return module


def host_available(adapter, mode):
    """Return None when the host can run this mode with its full powers, else the reason it cannot."""
    if shutil.which(adapter.CLI) is None:
        return f"command '{adapter.CLI}' not found on PATH"
    return adapter.missing_requirements(mode)


# ---- provenance -------------------------------------------------------------

def tree_hash(folder, replace=None, skip=(), exclude=()):
    """sha256 over every file's relative path and bytes. `replace` maps a relative path to new text.

    `skip` holds relative paths to leave out, `exclude` folders (such as a results folder) to leave out.
    """
    folder, replace, digest = Path(folder), replace or {}, hashlib.sha256()
    excluded = [Path(e).resolve() for e in exclude]
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        relative = path.relative_to(folder).as_posix()
        if relative in skip or any(path.resolve().is_relative_to(e) for e in excluded):
            continue
        data = replace[relative].encode("utf-8") if relative in replace else path.read_bytes()
        digest.update(relative.encode("utf-8") + b"\0" + hashlib.sha256(data).digest())
    return digest.hexdigest()


def repo_commit(repo=REPO_ROOT):
    """HEAD of the harnesswright checkout, with '-dirty' when tracked files changed, or None."""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True)
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo,
                               capture_output=True, text=True)
    except OSError:
        return None
    if head.returncode != 0:
        return None
    return head.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")


def host_version(adapter):
    """First line of `<CLI> --version`, or None."""
    try:
        done = subprocess.run([adapter.CLI, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = (done.stdout or done.stderr).strip().splitlines()
    return lines[0].strip() if done.returncode == 0 and lines else None


def provenance(adapter, mode, model, skill_path, skill_text, evals_file, results=None):
    """What produced a set of results, so a label can be traced and reproduced.

    The eval hash covers the trigger file for trigger runs, and for task runs the task file's folder
    (task file, input files and checks) without the trigger file and the `results` folder.
    """
    evals_file = Path(evals_file)
    evals = hashlib.sha256(evals_file.read_bytes()).hexdigest() if mode == "trigger" else \
        tree_hash(evals_file.parent, skip={"triggers.json"}, exclude=[results] if results else [])
    return {"runner_commit": repo_commit(), "host_version": host_version(adapter),
            "requested_model": model, "permission_profile": adapter.permission_profile(mode),
            "skill_sha256": tree_hash(skill_path, {"SKILL.md": skill_text}), "evals_sha256": evals}


def model_of(seen, requested):
    """The one model that produced results: what the host reported, else what was requested."""
    seen = sorted(set(m for m in seen if m))
    if len(seen) > 1:
        return "mixed: " + ", ".join(seen)
    return seen[0] if seen else requested


# ---- skill and eval files ---------------------------------------------------

def read_frontmatter(skill_md_text):
    """Return (frontmatter lines, body) of a SKILL.md, or raise EvalError."""
    lines = skill_md_text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise EvalError("SKILL.md has no opening '---'")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[1:index], "\n".join(lines[index + 1:])
    raise EvalError("SKILL.md has no closing '---'")


def _top_level_value(lines, key):
    """Value of a top-level key, joining an indented block scalar if used."""
    for index, line in enumerate(lines):
        if not line.startswith(f"{key}:"):
            continue
        value = line[len(key) + 1:].strip()
        if value in (">", "|", ">-", "|-"):
            block = []
            for follow in lines[index + 1:]:
                if not follow.startswith((" ", "\t")):
                    break
                block.append(follow.strip())
            return " ".join(block)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            return json.loads(value) if value[0] == '"' else value[1:-1]
        return value
    return None


def read_skill(skill_path):
    """Return (name, description, SKILL.md text) of a skill folder."""
    skill_md = Path(skill_path) / "SKILL.md"
    if not skill_md.is_file():
        raise EvalError(f"no SKILL.md in {skill_path}")
    text = skill_md.read_text(encoding="utf-8")
    lines, _ = read_frontmatter(text)
    name = _top_level_value(lines, "name")
    description = _top_level_value(lines, "description")
    if not name or not description:
        raise EvalError(f"{skill_md} needs both name and description")
    return name, description, text


def replace_description(skill_md_text, description):
    """Return SKILL.md text with the top-level description replaced."""
    lines, body = read_frontmatter(skill_md_text)
    kept, skipping = [], False
    for line in lines:
        if line.startswith("description:"):
            kept.append("description: " + json.dumps(description))
            skipping = True
            continue
        if skipping and line.startswith((" ", "\t")):
            continue
        skipping = False
        kept.append(line)
    return "\n".join(["---"] + kept + ["---"]) + "\n" + body


def load_triggers(path, skill_name):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("skill_name") != skill_name:
        raise EvalError(f"{path}: skill_name is not '{skill_name}'")
    queries = data.get("queries") or []
    ids = [q.get("id") for q in queries]
    if not queries or len(set(ids)) != len(ids) or None in ids:
        raise EvalError(f"{path}: queries must be non-empty with unique ids")
    for query in queries:
        if not isinstance(query.get("query"), str) or not isinstance(query.get("should_trigger"), bool):
            raise EvalError(f"{path}: query {query.get('id')} needs a query string and should_trigger")
    return queries


def load_tasks(path, skill_name):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("skill_name") != skill_name:
        raise EvalError(f"{path}: skill_name is not '{skill_name}'")
    tasks = data.get("tasks") or []
    if not tasks or len({t.get("id") for t in tasks}) != len(tasks):
        raise EvalError(f"{path}: tasks must be non-empty with unique ids")
    for task in tasks:
        if not task.get("name") or not task.get("prompt") or not task.get("expectations"):
            raise EvalError(f"{path}: task {task.get('id')} needs name, prompt and expectations")
    return tasks


def split_queries(queries, holdout, seed=42):
    """Split into (train ids, test ids), stratified by should_trigger, same result every run."""
    if holdout <= 0:
        return [q["id"] for q in queries], []
    rng = random.Random(seed)
    train, test = [], []
    for wanted in (True, False):
        group = sorted(q["id"] for q in queries if q["should_trigger"] is wanted)
        rng.shuffle(group)
        cut = max(1, int(len(group) * holdout)) if group else 0
        test += group[:cut]
        train += group[cut:]
    return sorted(train), sorted(test)


# ---- workspaces and host runs -----------------------------------------------

def _copy_ignore(excluded):
    """copytree ignore function: skip .git and every path in `excluded` (resolved paths)."""
    excluded = {Path(p).resolve() for p in excluded}

    def ignore(folder, names):
        here = Path(folder).resolve()
        return {n for n in names if n == ".git" or (here / n).resolve() in excluded}
    return ignore


def make_workspace(adapter, skill_path, skill_name, skill_text=None, base=None, exclude=()):
    """Create a disposable workspace, copy `base` into it (without `exclude`) and install the skill.

    Any copy of the skill that came with `base` is removed first, so a baseline run never sees it.
    """
    workspace = Path(tempfile.mkdtemp(prefix="hw-eval-"))
    if base is not None:
        shutil.copytree(base, workspace, dirs_exist_ok=True, ignore=_copy_ignore(exclude))
    for folder in SKILL_FOLDERS:
        shutil.rmtree(workspace / folder / skill_name, ignore_errors=True)
    shutil.rmtree(adapter.skill_dir(workspace, skill_name), ignore_errors=True)
    if skill_path is not None:
        target = adapter.skill_dir(workspace, skill_name)
        shutil.copytree(skill_path, target, dirs_exist_ok=True)
        if skill_text is not None:
            (target / "SKILL.md").write_text(skill_text, encoding="utf-8")
    return workspace


def run_host(adapter, workspace, prompt, mode, model, timeout):
    """Run the host once with the prompt on stdin. Returns a dict; never raises on host failure.

    A task run gets a scratch folder outside the workspace for tool caches (XDG_CACHE_HOME), so
    tools such as `go test` work inside every host's sandbox. A task run in which the host refused
    any action is a failed run: it did not have the powers the task needs.
    """
    scratch = Path(tempfile.mkdtemp(prefix="hw-scratch-")) if mode == "task" else None
    command = adapter.build_command(mode, Path(workspace), model, scratch)
    env = adapter.environment(dict(os.environ))
    if scratch:
        env["XDG_CACHE_HOME"] = str(scratch / "cache")
    timed_out = False
    try:
        done = subprocess.run(command, input=prompt, capture_output=True, text=True,
                              cwd=workspace, env=env, timeout=timeout)
        stdout, stderr, returncode = done.stdout, done.stderr, done.returncode
    except subprocess.TimeoutExpired as expired:
        stdout = _text(expired.stdout)
        stderr = _text(expired.stderr)
        returncode, timed_out = None, True
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)
    events = adapter.parse_events(stdout)
    refused = adapter.refusals(events)
    failure = adapter.failure(events, returncode, timed_out, mode)
    if failure is None and mode == "task" and refused:
        failure = f"host refused {len(refused)} action(s), first: {refused[0]}"
    return {"command": command, "events": events, "stdout": stdout, "stderr": stderr,
            "returncode": returncode, "timed_out": timed_out, "refusals": refused,
            "model": adapter.resolved_model(events), "failure": failure}


def _text(value):
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


# ---- scoring ----------------------------------------------------------------

def score_query(query, outcomes, threshold=0.5):
    """outcomes: list of True, False or None (None = run failed). Failed runs are not counted."""
    counted = [o for o in outcomes if o is not None]
    result = {"id": query["id"], "query": query["query"], "should_trigger": query["should_trigger"],
              "runs": len(counted), "errors": len(outcomes) - len(counted),
              "triggers": sum(1 for o in counted if o)}
    if not counted:
        result.update(trigger_rate=None, passed=None)
        return result
    rate = result["triggers"] / len(counted)
    result["trigger_rate"] = round(rate, 4)
    result["passed"] = rate >= threshold if query["should_trigger"] else rate < threshold
    return result


def summarise_queries(results, ids=None):
    chosen = [r for r in results if ids is None or r["id"] in ids]
    scored = [r for r in chosen if r["passed"] is not None]
    passed = sum(1 for r in scored if r["passed"])
    return {"total": len(chosen), "scored": len(scored), "passed": passed,
            "not_run": len(chosen) - len(scored),
            "accuracy": round(passed / len(scored), 4) if scored else None}


def task_passed(check_results, grading):
    """A task run passes when every expectation passed. Returns None while any is ungraded."""
    verdicts = {c["text"]: c["passed"] for c in check_results}
    if grading is not None:
        for item in grading.get("expectations", []):
            if item["text"] in verdicts and verdicts[item["text"]] is None:
                verdicts[item["text"]] = bool(item["passed"])
    return None if None in verdicts.values() else all(verdicts.values())


def summarise_task_runs(runs):
    """Per-task and overall statistics of scored runs, like skill-creator's benchmark (mean, stddev)."""
    tasks = {}
    for run in runs:
        tasks.setdefault(run["task_name"], []).append(run["passed"])
    per_task = {}
    for name, outcomes in sorted(tasks.items()):
        scored = [1.0 if o else 0.0 for o in outcomes if o is not None]
        per_task[name] = {"runs": len(outcomes), "scored": len(scored), "passed": int(sum(scored)),
                          "pass_rate": round(sum(scored) / len(scored), 4) if scored else None}
    outcomes = [1.0 if r["passed"] else 0.0 for r in runs if r["passed"] is not None]
    mean = sum(outcomes) / len(outcomes) if outcomes else None
    stddev = (sum((o - mean) ** 2 for o in outcomes) / (len(outcomes) - 1)) ** 0.5 \
        if len(outcomes) > 1 else None
    return {"tasks": per_task, "min_runs_per_task": min((t["scored"] for t in per_task.values()), default=0),
            "mean": round(mean, 4) if mean is not None else None,
            "stddev": round(stddev, 4) if stddev is not None else None}


def label_host(entry, reference, thresholds=THRESHOLDS):
    """Label one host and model pairing: verified, unsupported, inconclusive or incomplete, with gaps.

    incomplete: a result is missing, or the model that produced it is unknown or mixed.
    inconclusive: too few runs to decide, or no lift over the baseline, so the evals cannot show the
    skill works. unsupported: enough runs, and a threshold is missed.
    """
    task_rate, trigger, baseline = (entry.get("task_pass_rate"), entry.get("trigger_accuracy"),
                                    entry.get("baseline_pass_rate"))
    if None in (task_rate, trigger, baseline) or entry.get("trigger_not_run", 0) > 0:
        return {"label": "incomplete", "gaps": ["not every eval has a result, baseline included"]}
    model = entry.get("model")
    if not model or model.startswith("mixed"):
        return {"label": "incomplete", "gaps": [f"the model behind the results is {model or 'unknown'}"]}
    few = [f"{kind} has only {count} run(s) where {thresholds['min_runs']} are needed"
           for kind, count in (("a trigger query", entry.get("trigger_min_runs", 0)),
                               ("a task", entry.get("task_min_runs", 0)),
                               ("a baseline task", entry.get("baseline_min_runs", 0)))
           if count < thresholds["min_runs"]]
    gaps = []
    if task_rate < thresholds["task_pass_rate"]:
        gaps.append(f"task pass rate {task_rate:.0%} below {thresholds['task_pass_rate']:.0%}")
    ref_rate = reference.get("task_pass_rate")
    if ref_rate is not None and ref_rate - task_rate > thresholds["max_gap"] + 1e-9:
        gaps.append(f"task pass rate {ref_rate - task_rate:.0%} below the reference host")
    if trigger < thresholds["trigger_accuracy"]:
        gaps.append(f"trigger accuracy {trigger:.0%} below {thresholds['trigger_accuracy']:.0%}")
    if few:
        return {"label": "inconclusive", "gaps": few + gaps}
    if gaps:
        return {"label": "unsupported", "gaps": gaps}
    if entry["lift"] <= thresholds["min_lift"] + 1e-9:
        return {"label": "inconclusive", "gaps": [
            f"no lift over the baseline ({task_rate:.0%} with the skill, {baseline:.0%} without)"]}
    return {"label": "verified", "gaps": []}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def warn(message):
    print(message, file=sys.stderr)
