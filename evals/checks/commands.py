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
  With `exit_code`, a matching program counts only when its own exit code is known to be that code, read as
  `shell.codes` reads it, the one reader the stop checks share: the command's code, or an echoed `$?` after it, with
  every program before it sure to continue, and never when the command's own code was not reported. When a
  matching program's own code is not known, and none is known to be that code, it is `undecidable`.
"""

import re

from checks import Check, Undecidable, is_pattern
from shell import codes, programs  # the one splitter the grader view also cuts commands by, and its code reader


def command_ran(bundle, pattern, ran, exit_code=None):
    commands = bundle.entries("command")
    named = [e for e in commands if any(re.match(pattern, text) for text in programs(e["command"]))]
    mentioned = [e for e in commands if e not in named and re.search(pattern, e["command"])]
    tried = [e for e in bundle.entries("blocked") if re.search(pattern, e["action"])]
    if exit_code is None:
        found, unsure = named, []
    else:
        own = [[c for text, c in codes(e["command"], e["exit_code"], e.get("output")) if re.match(pattern, text)]
               for e in named]  # the own exit code of each matching program, or None where it is not known
        found = [e for e, known in zip(named, own) if exit_code in known]
        unsure = [e for e, known in zip(named, own) if e not in found and None in known]
    ended = "" if exit_code is None else f", ending with exit code {exit_code},"
    if found:
        first = found[0]["command"][:200]
        return ("pass" if ran else "fail"), f"{len(found)} commands matching {pattern!r}{ended} ran, the first: {first}"
    if tried and not ran:  # a refused try is never-run's one sure breach, so it decides before anything unsure
        return "fail", f"no command matching {pattern!r} ran, but one was tried and refused: {tried[0]['action'][:200]}"
    if unsure:  # a code `shell.codes` cannot give, such as one nobody saw or another program's, decides nothing
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
