"""Checks of the commands a run ran, read from the action log's command and blocked entries. An entry of either kind
that the host did not observe makes them `undecidable` (`checks.Bundle.entries`).

- `command_ran`: a program matching the regular expression `pattern` ran (`ran` true), or was never run nor tried
  (`ran` false). The pattern is matched where a program starts (`shell.programs`): at the start of the command, after an
  operator outside quotes (`&&`, `||`, `;`, `|`), after any `NAME=value` words, and the same way inside the script
  of a shell's `-c` flag (`bash -lc 'go test ./...'`). A command with a line break is read only from its start, since
  a later line may be a heredoc's text. So a program's quoted argument, such as the words a search looks for
  (`grep -c 'go test' README.md`), never counts. A command that holds a match anywhere else, such as after a wrapper
  (`timeout 60 go test`), may or may not have run it, so when only such commands match, it is `undecidable`. An
  action the host or the jail refused that matches the pattern anywhere is a try.
  With `exit_code`, a command that counts must also have ended with that code, and that code must be known to be
  its own program's (`shell.owns_exit_code`). When only commands whose code may be another program's match, or a
  matching command's code was not reported, it is `undecidable`.
"""

import re

from checks import Check, Undecidable, is_pattern
from shell import owns_exit_code, programs  # the one splitter the grader view also cuts commands by


def command_ran(bundle, pattern, ran, exit_code=None):
    commands = bundle.entries("command")
    named = [e for e in commands if any(re.match(pattern, text) for text in programs(e["command"]))]
    mentioned = [e for e in commands if e not in named and re.search(pattern, e["command"])]
    tried = [e for e in bundle.entries("blocked") if re.search(pattern, e["action"])]
    if exit_code is None:
        found, unsure = named, []
    else:
        alone = [e for e in named if owns_exit_code(e["command"], exit_code) and e["exit_code"] is not None]
        found = [e for e in alone if e["exit_code"] == exit_code]
        unsure = [e for e in named if e not in alone]
    ended = "" if exit_code is None else f", ending with exit code {exit_code},"
    if found:
        first = found[0]["command"][:200]
        return ("pass" if ran else "fail"), f"{len(found)} commands matching {pattern!r}{ended} ran, the first: {first}"
    if tried and not ran:  # a refused try is never-run's one sure breach, so it decides before anything unsure
        return "fail", f"no command matching {pattern!r} ran, but one was tried and refused: {tried[0]['action'][:200]}"
    if unsure:  # a code nobody saw, such as after a timeout, or the code of another command, decides nothing
        raise Undecidable(f"a command matching {pattern!r} ran, but its own exit code is not known: "
                          f"{unsure[0]['command'][:200]}", unsure)
    if mentioned:  # the match is not where a program starts, so the command may not have run it
        raise Undecidable(f"a command holds a match of {pattern!r}, but not where a program starts: "
                          f"{mentioned[0]['command'][:200]}", mentioned)
    return ("fail" if ran else "pass"), f"no command matching {pattern!r}{ended} ran"


CHECKS = {
    "command_ran": Check(command_ran, {"pattern": is_pattern, "ran": lambda v: isinstance(v, bool),
                                       "exit_code": lambda v: isinstance(v, int) and not isinstance(v, bool)},
                         optional=("exit_code",), about="a command matching a pattern ran, or was never run nor tried"),
}
