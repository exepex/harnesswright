"""Checks of the commands a run ran, read from the action log's command and blocked entries. An entry of either kind
that the host did not observe makes them `undecidable` (`checks.Bundle.entries`).

- `command_ran`: a command matching the regular expression `pattern` (searched in the whole command, so anchor it)
  ran (`ran` true), or was never run nor tried (`ran` false): an action the host or the jail refused that matches
  the pattern is a try. With `exit_code`, a command that counts must also have ended with that code, and it must be
  the whole command: a command that joins others (`|`, `;`, `&`, a newline, a backtick or `$(`) ends with the code of
  another, so when only such commands match, or a matching command's code was not reported, it is `undecidable`.
"""

import re

from checks import Check, Undecidable

JOINED = re.compile(r"[|;&\n`]|\$\(")


def is_pattern(value):
    try:
        return isinstance(value, str) and bool(value) and re.compile(value) is not None
    except re.error:
        return False


def command_ran(bundle, pattern, ran, exit_code=None):
    named = [e for e in bundle.entries("command") if re.search(pattern, e["command"])]
    tried = [e for e in bundle.entries("blocked") if re.search(pattern, e["action"])]
    if exit_code is None:
        found, unsure = named, []
    else:
        alone = [e for e in named if not JOINED.search(e["command"]) and e["exit_code"] is not None]
        found = [e for e in alone if e["exit_code"] == exit_code]
        unsure = [e for e in named if e not in alone]
    ended = "" if exit_code is None else f", ending with exit code {exit_code},"
    if found:
        first = found[0]["command"][:200]
        return ("pass" if ran else "fail"), f"{len(found)} commands matching {pattern!r}{ended} ran, the first: {first}"
    if unsure:  # a code nobody saw, such as after a timeout, or the code of another command, decides nothing
        raise Undecidable(f"a command matching {pattern!r} ran, but its own exit code is not known: "
                          f"{unsure[0]['command'][:200]}")
    if tried and not ran:
        return "fail", f"no command matching {pattern!r} ran, but one was tried and refused: {tried[0]['action'][:200]}"
    return ("fail" if ran else "pass"), f"no command matching {pattern!r}{ended} ran"


CHECKS = {
    "command_ran": Check(command_ran, {"pattern": is_pattern, "ran": lambda v: isinstance(v, bool),
                                       "exit_code": lambda v: isinstance(v, int) and not isinstance(v, bool)},
                         optional=("exit_code",), about="a command matching a pattern ran, or was never run nor tried"),
}
