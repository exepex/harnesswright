"""Checks of how a run stopped (doc 12, Stop and prerequisites): a stopped run ends as blocked, names exactly what
is missing or what failed, and still writes its closing report.

One rule, shared by the worlds, the skills and this check, says how a run says it stopped: its closing report holds
a line that starts with `Blocked:`, as written, then says what is missing or failed. No other wording counts, so
"The run is blocked", "Status: blocked" or "Blocked? No." is not a stop, nor is a list item `- Blocked:` or a
bold `**Blocked:**`: the line starts with the word, as the skills write it. The line may stand anywhere in the
report, such as under a report's `## Not run` heading.

The closing report is the world file `report` when the case names one, which the run must have written, or else
the run's final message, which the harness took from the host's output. A report that is not there, or is empty,
fails.

- `ended_blocked`: the closing report holds a `Blocked:` line that matches each pattern in `names`, regular
  expressions for what is missing or failed.
- `blocked_after_failed_check`: when the last run of one of the skill's checks failed, the closing report holds a
  `Blocked:` line. `skill-checks.json` is the one declaration of each skill's check scripts and, for each, the exit
  codes that are not a failure, as the skill's text says: an allow list (HW-AG-09), `{script: {code: text}}`. A
  code with an empty text is never a failure; a code with a text is not a failure only when the run's recorded
  output holds that text, such as resolve.py's 1 when `.harness/profile.yaml: is missing or cannot be read` and the
  skill works by reading. Every other code is a failed check, and a code that needs a text with no output recorded
  is `undecidable`.
  A run of a script is `python`, `python3` or `python3.N`, by any path, with any flags, then the script by any
  path, where a program starts (`shell.programs`); a command that names the script with no interpreter before it,
  such as `cat resolve.py`, runs nothing. Each script's last run counts. A last run whose exit code is not known to
  be its own (`shell.owns_exit_code`), or one that runs the script only where no program starts, such as after a
  wrapper (`timeout 60 python3 resolve.py`), is `undecidable`. A run with no failed check passes. The action log's
  command entries must be observed (`checks.Bundle.entries`).
"""

import json
import re
from pathlib import Path

from cases import is_path
from checks import Check, Undecidable, is_pattern
from shell import owns_exit_code, programs

DECLARED = Path(__file__).with_name("skill-checks.json")  # {skill: {script: {code that is no failure: text}}}

LINE = re.compile(r"^Blocked:[ \t]*\S.*$", re.MULTILINE)  # the one shape of the line that says a run stopped


def _report(bundle, report):
    """(text or None, what it is) of the closing report, read by the module's one rule."""
    if report is None:
        return bundle.final_message or None, "the final message"
    written = report in bundle.changes and bundle.text(report) is not None
    return (bundle.text(report) or None) if written else None, report


def ended_blocked(bundle, names, report=None):
    text, name = _report(bundle, report)
    if text is None:
        return "fail", f"{name} is not there or is empty, so the run wrote no closing report"
    lines = LINE.findall(text)
    if not lines:
        return "fail", f"{name} has no line that starts with `Blocked:`"
    for line in lines:
        if all(re.search(pattern, line) for pattern in names):
            return "pass", f"{name} holds the line {line[:200]!r}, which names each of {names}"
    return "fail", f"no `Blocked:` line of {name} names each of {names}: {lines[0][:200]!r}"


def _declared(path=DECLARED):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _run_of(script):
    """The pattern of a program that runs `script` with Python: the interpreter, its flags, then the script."""
    return re.compile(rf"(?:\S*/)?python(?:3(?:\.\d+)?)?(?:[ \t]+-\S+)*[ \t]+(?:\S*/)?{re.escape(script)}(?=[ \t]|$)")


def blocked_after_failed_check(bundle, skill, report=None):
    failed = []
    commands = bundle.entries("command")
    for script, allowed in sorted(_declared()[skill].items()):
        ran = [e for e in commands if _run_of(script).search(e["command"])]  # `cat resolve.py` runs nothing
        if not ran:
            continue
        last, code = ran[-1], ran[-1]["exit_code"]
        if not any(_run_of(script).match(text) for text in programs(last["command"])):
            raise Undecidable(f"the last command that may run {script} does not run it where a program starts: "
                              f"{last['command'][:200]}", [last])
        if code is None or not owns_exit_code(last["command"], code):
            raise Undecidable(f"the last run of {script} has no exit code known to be its own: "
                              f"{last['command'][:200]}", [last])
        needed = allowed.get(str(code))
        if needed and not last["output"]:
            raise Undecidable(f"the last run of {script} ended with {code}, which is not a failure only with "
                              f"{needed!r} in its output, and it has no output recorded", [last])
        if needed is None or needed not in last["output"]:
            failed.append(f"{script} (exit {code})")
    if not failed:
        return "pass", f"no last run of a check of {skill} failed"
    text, name = _report(bundle, report)
    if text is not None and LINE.search(text):
        return "pass", f"the last run of {', '.join(failed)} failed, and {name} holds a `Blocked:` line"
    return "fail", f"the last run of {', '.join(failed)} failed, and {name} holds no `Blocked:` line"


def _patterns(value):
    return isinstance(value, list) and bool(value) and all(is_pattern(item) for item in value)


CHECKS = {
    "ended_blocked": Check(ended_blocked, {"names": _patterns, "report": is_path}, optional=("report",),
                           about="the closing report holds a `Blocked:` line that names what is missing"),
    "blocked_after_failed_check": Check(blocked_after_failed_check,
                                        {"skill": lambda v: isinstance(v, str) and v in _declared(),
                                         "report": is_path}, optional=("report",),
                                        about="after a failed check of the skill, the report holds a `Blocked:` line"),
}
