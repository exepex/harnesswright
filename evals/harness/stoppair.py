"""The stop pair (doc 12, Stop and prerequisites): the two expectations every task case of a skill with check
scripts is asked and does not write, appended by `cases.Case` before the done question.

A grader never overrules a check, so the stop is asked in two parts: `blocked_after_failed_check` on the case's
skill (`evals/checks/stops.py`), whose judged question the graders answer only when the check cannot decide, and a
judged question alone, whether the `Blocked:` line names the failed script and what it printed. Both questions
name the skill's scripts and the exit codes that are no failure, from the one declaration of them,
`evals/checks/skill-checks.json` (`skill_checks`), which the check reads too. Where no script ran, as when the
profile forbids scripts, no check failed: the check passes, and both questions read as passed.

Standard library only.
"""

import json
from pathlib import Path

from cases import REPO, CaseError, is_expectation, is_name

STOP = REPO / "evals" / "grading" / "stop.json"  # the pair's text, with {skill} and {checks} to fill
SKILL_CHECKS = REPO / "evals" / "checks" / "skill-checks.json"  # {skill: {script: {code that is no failure: text}}}


def skill_checks(path=None):
    """{skill: {script: {exit code that is no failure: the text its output must hold, or ""}}}: the one declaration
    of each skill's check scripts, which the stop check reads too (`stops.py`)."""
    path = Path(path or SKILL_CHECKS)
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaseError(f"{path.name}: {error}") from None
    if not (isinstance(data, dict) and all(is_name(k) and isinstance(v, dict) and v and all(
            isinstance(script, str) and isinstance(codes, dict) and codes and all(
                code.isdigit() and isinstance(text, str) for code, text in codes.items())
            for script, codes in v.items()) for k, v in data.items())):
        raise CaseError(f"{path.name}: must map each skill to {{script: {{exit code: text}}}}")
    return data


def _codes(script, codes):
    """How one script's last run fails, in words: every exit code but those `codes` names, each with its text."""
    kept = [code if not text else f"{code} with `{text}` in its output" for code, text in codes.items()]
    allowed = kept[0] if len(kept) == 1 else ", ".join(kept[:-1]) + f" or {kept[-1]}"
    return f"the last run of its {script} ended with any exit code but {allowed}"


def stop(skill, path=None, declared=None):
    """The stop pair of `skill`'s task cases: each of an expectation's shape, with source `"stop"`, the first decided
    by `blocked_after_failed_check` on `skill`, the second by graders only, each question naming the skill's scripts
    and the codes that are no failure (`skill_checks`)."""
    scripts = (declared if declared is not None else skill_checks())[skill]
    checks = ", or ".join(_codes(script, codes) for script, codes in sorted(scripts.items()))
    path = Path(path or STOP)
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaseError(f"{path.name}: {error}") from None
    checked = {"name": "blocked_after_failed_check", "args": {"skill": "{skill}"}}
    if not (isinstance(data, list) and len(data) == 2 and data[0].get("check") == checked
            and "check" not in data[1] and all(isinstance(e, dict) and e.get("source") == "stop"
                                               and is_expectation({**e, "source": "format"}) for e in data)):
        raise CaseError(f"{path.name}: the stop pair is a checked and a judged expectation, source \"stop\"")
    pair = json.loads(json.dumps(data))
    pair[0]["check"]["args"]["skill"] = skill
    for expectation in pair:
        expectation["judged"]["question"] = expectation["judged"]["question"].replace("{checks}", checks)
    return pair
