"""Checks of the commands a run ran, read from the action log's command and blocked entries. An entry of either kind
that the host did not observe makes them `undecidable` (`checks.Bundle.entries`).

- `command_ran`: a program matching the regular expression `pattern` ran (`ran` true), or was never run nor tried
  (`ran` false). The pattern is matched where a program starts (`programs`): at the start of the command, after an
  operator outside quotes (`&&`, `||`, `;`, `|`, a line break), after any `NAME=value` words, and the same way
  inside the script of a shell's `-c` flag (`bash -lc 'go test ./...'`). So a program's quoted argument, such as the
  words a search looks for (`grep -c 'go test' README.md`), never counts. A command that holds a match anywhere
  else, such as after a wrapper (`timeout 60 go test`), may or may not have run it, so when only such commands
  match, it is `undecidable`. An action the host or the jail refused that matches the pattern anywhere is a try.
  With `exit_code`, a command that counts must also have ended with that code, and it must be one whose code is
  known to be its own (`ALONE`): one program with its arguments, each a plain word, a simple quoted string of a
  plain word's characters and blanks, or a redirect such as `2>&1`; or, for exit code 0 only, such programs joined
  by `&&`, which ends with 0 only when each did. Any other shape, such as a pipe, `||`, `;` or `$(`, may end with
  the code of another program, so when only such commands match, or a matching command's code was not reported, it
  is `undecidable`. A quoted string with any other character may be a script that a program runs
  (`bash -c '... | tail'`), so it is not plain.
"""

import re

from checks import Check, Undecidable

# The one shape of a command whose exit code is its own program's: plain words, simple quoted strings, redirects.
# A quoted string holds only a plain word's characters and blanks, since a program such as bash -c may run it as a
# script, and any other character (an operator, a line break, !) could make that script end with another code.
PLAIN = r"[A-Za-z0-9_./=:@%+,*?~\[\]-]"
QUOTED = r"[A-Za-z0-9_./=:@%+,*?~\[\] \t-]"  # a plain word's characters and blanks
WORD = rf"""(?:{PLAIN}|'{QUOTED}*'|"{QUOTED}*")+"""
TOKEN = rf"(?:\d*>&\d+|(?:&|\d*)>>?[ \t]*{WORD}|<[ \t]*{WORD}|{WORD})"
PROGRAM = rf"[ \t]*{TOKEN}(?:[ \t]+{TOKEN})*[ \t]*"
ALONE = re.compile(PROGRAM)
CHAIN = re.compile(rf"{PROGRAM}(?:&&{PROGRAM})*")  # ends with 0 only when every program did


def is_pattern(value):
    try:
        return isinstance(value, str) and bool(value) and re.compile(value) is not None
    except re.error:
        return False


# Where a program starts: after an operator outside quotes, then after any NAME=value words. A shell's -c script is
# a command of its own.
OPERATOR = re.compile(r"&&|\|\||[;|\n]")
ASSIGNMENT = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_]*=\S*[ \t]+)*")
SHELL_SCRIPT = re.compile(r"(?:\S*/)?(?:bash|sh|zsh|dash)[ \t]+-[A-Za-z]*c[ \t]+('[^']*'|\"[^\"]*\")")


def programs(command):
    """The text from each place a program starts in `command` to its end."""
    starts, quote, i = [0], None, 0
    while i < len(command):
        char = command[i]
        if quote:
            quote = None if char == quote else quote
        elif char in "'\"":
            quote = char
        elif match := OPERATOR.match(command, i):
            i = match.end()
            starts.append(i)
            continue
        i += 1
    found = []
    for start in starts:
        text = command[start:].lstrip(" \t")
        text = text[ASSIGNMENT.match(text).end():]
        found.append(text)
        if script := SHELL_SCRIPT.match(text):
            found += programs(script.group(1)[1:-1])
    return found


def command_ran(bundle, pattern, ran, exit_code=None):
    commands = bundle.entries("command")
    named = [e for e in commands if any(re.match(pattern, text) for text in programs(e["command"]))]
    mentioned = [e for e in commands if e not in named and re.search(pattern, e["command"])]
    tried = [e for e in bundle.entries("blocked") if re.search(pattern, e["action"])]
    if exit_code is None:
        found, unsure = named, []
    else:
        shape = CHAIN if exit_code == 0 else ALONE
        alone = [e for e in named if shape.fullmatch(e["command"]) and e["exit_code"] is not None]
        found = [e for e in alone if e["exit_code"] == exit_code]
        unsure = [e for e in named if e not in alone]
    ended = "" if exit_code is None else f", ending with exit code {exit_code},"
    if found:
        first = found[0]["command"][:200]
        return ("pass" if ran else "fail"), f"{len(found)} commands matching {pattern!r}{ended} ran, the first: {first}"
    if unsure:  # a code nobody saw, such as after a timeout, or the code of another command, decides nothing
        raise Undecidable(f"a command matching {pattern!r} ran, but its own exit code is not known: "
                          f"{unsure[0]['command'][:200]}")
    if mentioned:  # the match is not where a program starts, so the command may not have run it
        raise Undecidable(f"a command holds a match of {pattern!r}, but not where a program starts: "
                          f"{mentioned[0]['command'][:200]}")
    if tried and not ran:
        return "fail", f"no command matching {pattern!r} ran, but one was tried and refused: {tried[0]['action'][:200]}"
    return ("fail" if ran else "pass"), f"no command matching {pattern!r}{ended} ran"


CHECKS = {
    "command_ran": Check(command_ran, {"pattern": is_pattern, "ran": lambda v: isinstance(v, bool),
                                       "exit_code": lambda v: isinstance(v, int) and not isinstance(v, bool)},
                         optional=("exit_code",), about="a command matching a pattern ran, or was never run nor tried"),
}
