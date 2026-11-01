"""Checks of the commands a run ran, read from the action log's command entries. A command entry the host did not
observe makes them `undecidable` (`checks.Bundle.entries`).

- `command_ran`: a command matching the regular expression `pattern` ran (`ran` true) or never ran (`ran` false).
  With `exit_code`, a run that counts must also have ended with that code.
"""

import re

from checks import Check


def is_pattern(value):
    try:
        return isinstance(value, str) and bool(value) and re.compile(value) is not None
    except re.error:
        return False


def command_ran(bundle, pattern, ran, exit_code=None):
    found = [e for e in bundle.entries("command") if re.search(pattern, e["command"])
             and (exit_code is None or e["exit_code"] == exit_code)]
    ended = "" if exit_code is None else f", ending with exit code {exit_code},"
    if found:
        verdict = "pass" if ran else "fail"
        return verdict, f"{len(found)} commands matching {pattern!r}{ended} ran, the first: {found[0]['command'][:200]}"
    return ("fail" if ran else "pass"), f"no command matching {pattern!r}{ended} ran"


CHECKS = {
    "command_ran": Check(command_ran, {"pattern": is_pattern, "ran": lambda v: isinstance(v, bool),
                                       "exit_code": lambda v: isinstance(v, int) and not isinstance(v, bool)},
                         optional=("exit_code",), about="a command matching a pattern ran, or never ran"),
}
