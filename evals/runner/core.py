"""Host-neutral eval runner core: eval files, workspaces, host runs and scoring.

Python 3 standard library only. The runner makes no network calls of its own; the host
command it starts does. Everything here is deterministic for the same inputs and host output.
"""

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
ADAPTER_FUNCTIONS = ("skill_dir", "build_command", "environment", "parse_events",
                     "skill_triggered", "final_message", "failure")
THRESHOLDS = {"task_pass_rate": 0.9, "max_gap": 0.10, "trigger_accuracy": 0.9}


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


def host_available(adapter):
    """Return None when the host command exists, else the reason it cannot run."""
    if shutil.which(adapter.CLI) is None:
        return f"command '{adapter.CLI}' not found on PATH"
    return None


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

def make_workspace(adapter, skill_path, skill_name, skill_text=None, base=None):
    """Create a disposable workspace, copy `base` into it and install the skill."""
    workspace = Path(tempfile.mkdtemp(prefix="hw-eval-"))
    if base is not None:
        shutil.copytree(base, workspace, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
    if skill_path is not None:
        target = adapter.skill_dir(workspace, skill_name)
        shutil.copytree(skill_path, target, dirs_exist_ok=True)
        if skill_text is not None:
            (target / "SKILL.md").write_text(skill_text, encoding="utf-8")
    return workspace


def run_host(adapter, workspace, prompt, mode, model, timeout):
    """Run the host once with the prompt on stdin. Returns a dict; never raises on host failure."""
    command = adapter.build_command(mode, Path(workspace), model)
    env = adapter.environment(dict(os.environ))
    timed_out = False
    try:
        done = subprocess.run(command, input=prompt, capture_output=True, text=True,
                              cwd=workspace, env=env, timeout=timeout)
        stdout, stderr, returncode = done.stdout, done.stderr, done.returncode
    except subprocess.TimeoutExpired as expired:
        stdout = _text(expired.stdout)
        stderr = _text(expired.stderr)
        returncode, timed_out = None, True
    events = adapter.parse_events(stdout)
    return {"command": command, "events": events, "stdout": stdout, "stderr": stderr,
            "returncode": returncode, "timed_out": timed_out,
            "failure": adapter.failure(events, returncode, timed_out)}


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


def label_host(entry, reference, thresholds=THRESHOLDS):
    """Label one host and model pairing: verified or unsupported, with the gaps found."""
    gaps = []
    task_rate, trigger = entry.get("task_pass_rate"), entry.get("trigger_accuracy")
    if task_rate is None or trigger is None:
        return {"label": "incomplete", "gaps": ["not every eval has a result"]}
    if task_rate < thresholds["task_pass_rate"]:
        gaps.append(f"task pass rate {task_rate:.0%} below {thresholds['task_pass_rate']:.0%}")
    ref_rate = reference.get("task_pass_rate")
    if ref_rate is not None and ref_rate - task_rate > thresholds["max_gap"] + 1e-9:
        gaps.append(f"task pass rate {ref_rate - task_rate:.0%} below the reference host")
    if trigger < thresholds["trigger_accuracy"]:
        gaps.append(f"trigger accuracy {trigger:.0%} below {thresholds['trigger_accuracy']:.0%}")
    return {"label": "unsupported" if gaps else "verified", "gaps": gaps}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def warn(message):
    print(message, file=sys.stderr)
