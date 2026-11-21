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
"""

import re

from cases import is_path
from checks import Check, is_pattern

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


def _patterns(value):
    return isinstance(value, list) and bool(value) and all(is_pattern(item) for item in value)


CHECKS = {
    "ended_blocked": Check(ended_blocked, {"names": _patterns, "report": is_path}, optional=("report",),
                           about="the closing report holds a `Blocked:` line that names what is missing"),
}
