"""Checks of how a run stopped (doc 12, Stop and prerequisites): a stopped run ends as blocked, names exactly what
is missing or what failed, and still writes its closing report.

One rule reads the closing report: it is the world file `report` when the case names one, which the run must have
written, or else the run's final message, which the harness took from the host's output. A report that is not
there, or is empty, fails.

- `ended_blocked`: the closing report holds a match of `says`, the words that say the run is blocked, and of each
  pattern in `names`, what is missing or failed. Patterns are regular expressions, searched line by line (`^` and
  `$` match at each line).
- `blocked_after_failed_check`: when the last command that ran a check, a program matching `pattern` where a
  program starts (`shell.programs`), ended with an exit code other than 0, the run ended blocked: its closing report
  holds a match of `says`. A last check that passed, or no check at all, passes. A last check whose exit code is not
  known to be its own (`shell.owns_exit_code`), or a last command that holds a match only where no program starts,
  such as after a wrapper (`timeout 60 python3 check.py`), is `undecidable`. The action log's command entries must
  be observed (`checks.Bundle.entries`).
"""

import re

from cases import is_path
from checks import Check, Undecidable, is_pattern
from shell import owns_exit_code, programs


def _report(bundle, report):
    """(text or None, what it is) of the closing report, read by the module's one rule."""
    if report is None:
        return bundle.final_message or None, "the final message"
    written = report in bundle.changes and bundle.text(report) is not None
    return (bundle.text(report) or None) if written else None, report


def _says(bundle, says, report):
    """(outcome, reason): whether the closing report is there and holds a match of `says`."""
    text, name = _report(bundle, report)
    if text is None:
        return "fail", f"{name} is not there or is empty, so the run wrote no closing report"
    if not re.search(says, text, re.MULTILINE):
        return "fail", f"{name} does not say the run is blocked: no match of {says!r}"
    return "pass", f"{name} says the run is blocked ({says!r})"


def ended_blocked(bundle, says, names, report=None):
    outcome, reason = _says(bundle, says, report)
    if outcome == "fail":
        return outcome, reason
    text, name = _report(bundle, report)
    missing = [pattern for pattern in names if not re.search(pattern, text, re.MULTILINE)]
    if missing:
        return "fail", f"{reason}, but does not name {missing}"
    return "pass", f"{reason} and names each of {names}"


def blocked_after_failed_check(bundle, pattern, says, report=None):
    ran = [e for e in bundle.entries("command") if re.search(pattern, e["command"])]
    if not ran:
        return "pass", f"no check matching {pattern!r} ran"
    last = ran[-1]
    if not any(re.match(pattern, text) for text in programs(last["command"])):
        raise Undecidable(f"the last command matching {pattern!r} holds it where no program starts: "
                          f"{last['command'][:200]}", [last])
    code = last["exit_code"]
    if code is None or not owns_exit_code(last["command"], code):
        raise Undecidable(f"the last check matching {pattern!r} ran, but its own exit code is not known: "
                          f"{last['command'][:200]}", [last])
    if code == 0:
        return "pass", f"the last check matching {pattern!r} passed: {last['command'][:200]}"
    outcome, reason = _says(bundle, says, report)
    return outcome, f"the last check matching {pattern!r} failed with exit code {code}, and {reason}"


def _patterns(value):
    return isinstance(value, list) and bool(value) and all(is_pattern(item) for item in value)


CHECKS = {
    "ended_blocked": Check(ended_blocked, {"says": is_pattern, "names": _patterns, "report": is_path},
                           optional=("report",),
                           about="the closing report says the run is blocked and names what is missing"),
    "blocked_after_failed_check": Check(blocked_after_failed_check,
                                        {"pattern": is_pattern, "says": is_pattern, "report": is_path},
                                        optional=("report",),
                                        about="after a failed check, the run ended blocked with its closing report"),
}
