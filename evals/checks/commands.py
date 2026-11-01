"""Checks of the commands a run ran, read from the action log's command entries. A command entry the host did not
observe makes them `undecidable` (`checks.Bundle.entries`).

- `command_ran`: a command matching the regular expression `pattern` ran (`ran` true) or never ran (`ran` false).
  With `exit_code`, a run that counts must also have ended with that code, and a matching command whose code
  was not reported makes it `undecidable`.
"""

import re

from checks import Check, Undecidable


def is_pattern(value):
    try:
        return isinstance(value, str) and bool(value) and re.compile(value) is not None
    except re.error:
        return False


def command_ran(bundle, pattern, ran, exit_code=None):
    named = [e for e in bundle.entries("command") if re.search(pattern, e["command"])]
    found = [e for e in named if exit_code is None or e["exit_code"] == exit_code]
    ended = "" if exit_code is None else f", ending with exit code {exit_code},"
    if found:
        first = found[0]["command"][:200]
        return ("pass" if ran else "fail"), f"{len(found)} commands matching {pattern!r}{ended} ran, the first: {first}"
    unseen = [e for e in named if e["exit_code"] is None]
    if exit_code is not None and unseen:  # a code nobody saw, such as after a timeout, decides nothing
        raise Undecidable(f"a command matching {pattern!r} ran, but its exit code was not reported: "
                          f"{unseen[0]['command'][:200]}")
    return ("fail" if ran else "pass"), f"no command matching {pattern!r}{ended} ran"


CHECKS = {
    "command_ran": Check(command_ran, {"pattern": is_pattern, "ran": lambda v: isinstance(v, bool),
                                       "exit_code": lambda v: isinstance(v, int) and not isinstance(v, bool)},
                         optional=("exit_code",), about="a command matching a pattern ran, or never ran"),
}
