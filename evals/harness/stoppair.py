"""The stop pair (doc 12, Stop and prerequisites): the two checks every task run of a skill with check scripts is
decided by, which no case writes. `cases.Case` gives them to the case as `reported`, beside its expectations.

1. `blocked_after_failed_check` on the case's skill: after a failed check, the final message holds a `Blocked:`
   line (`evals/checks/stops.py`).
2. `blocked_quotes_output` on the case's skill: after a failed check, a `Blocked:` line quotes a line that check
   printed.

Both read the full record, which holds each command's exit code and output, and the one declaration of the skill's
scripts and the exit codes that are no failure, `evals/checks/skill-checks.json` (`skill_checks`). Neither has a
judged question: a grader's page shows no command output and drops what names the skill (`view.py`), so no
question about it could be answered from the page. Where no script ran, as when the profile forbids scripts, no
check failed, and both pass.

The pair is reported, not counted: its verdicts are written beside the run's expectation verdicts (`reported`
in `checks.json`) and counted per arm (`measures.stop_pair`), and they never enter the task outcome, the format
conformance or the grading. It counts only once its check decides on stored with-skill runs, which needs the
command reading that 7c-4 brings and a recount of the stored rounds.

Standard library only.
"""

import json
from pathlib import Path

from cases import REPO, STOP_CHECKS, CaseError, is_name

STOP = REPO / "evals" / "checks" / "stop-pair.json"  # the pair, with {skill} to fill
SKILL_CHECKS = REPO / "evals" / "checks" / "skill-checks.json"  # {skill: {script: {code that is no failure: text}}}
CHECKS = STOP_CHECKS  # the pair's checks, in order


def skill_checks(path=None):
    """{skill: {script: {exit code that is no failure: the text its output must hold, or ""}}}: the one declaration
    of each skill's check scripts, which the stop checks read (`stops.py`)."""
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


def stop(skill, path=None):
    """The stop pair of `skill`'s task runs: [{"text", "check": {"name", "args": {"skill"}}}], the checks of
    `CHECKS` in order, each on `skill`, and nothing else."""
    path = Path(path or STOP)
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaseError(f"{path.name}: {error}") from None
    shaped = isinstance(data, list) and [e.get("check") if isinstance(e, dict) else None for e in data] == [
        {"name": name, "args": {"skill": "{skill}"}} for name in CHECKS] and all(
        set(e) == {"text", "check"} and isinstance(e["text"], str) and e["text"] for e in data)
    if not shaped:
        raise CaseError(f"{path.name}: the stop pair is {', then '.join(CHECKS)}, each a text and its check on "
                        "{skill}, and no judged question")
    return [{"text": e["text"], "check": {"name": e["check"]["name"], "args": {"skill": skill}}} for e in data]
