"""Where the programs of a shell command start: the one splitter the command checks (`evals/checks/commands.py`) and
the grader view (`view.py`) share, so the two never disagree on it.

- `programs(command)`: the text from each place a program starts to the command's end. A program starts at the
  start of the command, after an operator outside quotes (`&&`, `||`, `;`, `|`), after any `NAME=value` words, and
  the same way inside the script of a shell's `-c` flag. A command with a line break is read only from its start,
  since a later line may be a heredoc's text.
- `words(command)`: the words of each program `programs` finds, as the shell splits them, quotes taken off, each
  program to the operator after it: None for a program it cannot split, such as one with an open quote or a line
  break, and nothing for a shell's `-c` program, whose script's programs are listed in its place.
- `cut(command, drop)`: the command without each of its pipelines that `drop` takes, or None when no clean cut is
  possible. A cut removes each pipeline `drop` takes and everything that depends on a removed pipeline: what reads
  its exit code (`$?`) or is joined to it by `&&` or `||`, down the chain. Each takes the operator before it with it
  (after it, for the first), so no operator is left at a seam. A command is cut
  only when it has one shape (`CUTTABLE`), in which the splitter's reading of quotes is exact, and every program it
  removes leaves the shell as it found it (`STATELESS`), so no later program reads a folder, a variable or an
  output it set.
- `plain(command)`: whether the command has the one shape whose programs can be read: on one line, programs of
  plain words, simple quoted strings, an escaped parenthesis and redirects, joined by `&&`, `||`, `;` and `|`, and
  no expansion but a variable's value (`$NAME`, `${NAME}`, `${NAME[0]}`, `$?`), which runs nothing. A substitution
  (`$(`, a backtick, `<(`), a group, a heredoc or any other construct may run a program the words do not show.
- `continues(text)`: whether the program `text` is sure to hand the shell on to what follows it: one of `CONTINUES`,
  an allow list of programs that never end or replace the shell, or assignments alone. `exit`, `exec`, `set`, a
  wrapper that runs another program, or a program by its path may not. A program proves it ran, and its exit code
  that it is its own, only when every program before it in the command continues (`exit_code`).
- `_owns_exit_code(command, code)`, which only `exit_code` uses: whether the command's exit code, when it is `code`,
  is its own program's. That holds for one program with its arguments, each a plain word, a simple quoted string of
  a plain word's characters and blanks, or a redirect such as `2>&1`; and, for code 0 only, for such programs joined
  by `&&`, which ends with 0 only when each did, each before the last one that `continues`. Any other shape, such as
  a pipe, `||`, `;` or `$(`, may end with another program's code. A plain word may hold a variable such as `$S`,
  which changes no exit code.
- `exit_code(command, program, code, output)`: the exit code of the top-level program numbered `program` (from 0, as
  `parts` counts them) of a command that ended with `code` and printed `output`, or None when it cannot be known. A
  command is a list of units, each a program at the start or after a `;` with what `&&`, `||` or `|` joins to it. One
  rule: the program's unit must be joined by `&&` only, and the program's code is the unit's code `c` when
  `_owns_exit_code(unit, c)`. That holds for a nonzero `c` only when the program is the unit's only one, and for 0 at
  any place in the unit, since a unit joined by `&&`, such as `cd x && run && echo ok`, ends with 0 only when each
  program did; a nonzero code may be an earlier program's, which stopped the unit before the run. No code is known when
  the command's own code was not reported: it may have been stopped before an `echo` after the run, so a line of that
  shape may be the run's own. Otherwise the unit's code is known two ways. The last unit gives the command's code, when
  every unit is plain programs joined by `&&` (`CHAIN`). Or the next unit is `echo <words>$?` alone: it prints its words
  and the code on a line of `output`. Each unit that may print a line that starts with those words is an `echo` of
  exactly those words and one value, alone in its unit so it always runs, and the output has one such line for each, in
  order; any other printer, or another count of lines, leaves it unknown. A pipe or other shape elsewhere on the line
  changes nothing; in the run's own unit it leaves the code unknown. Either way every program before it must continue.
- `codes(command, code, output)`: [(text, exit code)] of each program `programs` finds, in its order: the code
  `exit_code` gives, or None. This is the one place a check reads a program's exit code, so two checks never read
  it two ways. A program in the script of a shell's `-c` flag gets the code `exit_code` gives it within that
  script, which ends with the shell's own code, and no output, since the rest of the command prints to it too.
- `parts(command)`: [(the operator before it, its text)] of each top-level program, as `programs` finds its starts.

Standard library only.
"""

import re
import shlex

OPERATOR = re.compile(r"&&|\|\||[;|]")
ASSIGNMENT = re.compile(r"""(?:[A-Za-z_][A-Za-z0-9_]*=(?:'[^']*'|"[^"]*"|[^\s'"])*[ \t]+)*""")
SHELL_SCRIPT = re.compile(r"(?:\S*/)?(?:bash|sh|zsh|dash)[ \t]+-[A-Za-z]*c[ \t]+('[^']*'|\"[^\"]*\")")

# The one shape of a command that can be cut: on one line, and outside quotes only a plain word's characters,
# blanks, a variable such as $? or $HOME, the operators and redirects; a quoted string holds no $(, backtick or
# backslash. So no subshell, group, substitution, heredoc, comment or background job spans a cut.
VARIABLE = r"\$[A-Za-z_?#0-9]"
OUTSIDE = rf"[A-Za-z0-9_./=:@%+,*?~\[\] \t-]|{VARIABLE}|&&|\|\||[;|]|\d*>>?(?:&\d+)?|&>>?|<(?!<)"
QUOTED = rf"""'[^'\n]*'|"(?:[^"\\`$\n]|{VARIABLE})*\""""
CUTTABLE = re.compile(rf"(?:{QUOTED}|{OUTSIDE})*")
# Programs that change no state of the shell, such as its folder or its variables. A program run by its path counts.
STATELESS = frozenset((
    "awk", "basename", "cat", "cmp", "cp", "cut", "diff", "dirname", "du", "echo", "env", "file", "find", "go",
    "grep", "head", "ls", "md5sum", "mkdir", "mv", "nl", "node", "python", "python3", "readlink",
    "realpath", "rm", "sed", "sha256sum", "sort", "stat", "tail", "test", "timeout", "touch", "tr", "tree", "uniq",
    "wc", "xargs"))


# The one shape of a command whose exit code is its own program's: plain words, simple quoted strings, redirects.
# A quoted string holds only a plain word's characters and blanks, since a program such as bash -c may run it as a
# script, and any other character (an operator, a line break, !) could make that script end with another code.
PLAIN = r"[A-Za-z0-9_./=:@%+,*?~\[\]-]"
PLAIN_QUOTED = r"[A-Za-z0-9_./=:@%+,*?~\[\] \t-]"  # a plain word's characters and blanks
VARIABLE_WORD = r"\$(?:[A-Za-z_][A-Za-z0-9_]*|\{[A-Za-z_][A-Za-z0-9_]*\})"  # `$S`: a value, never a program
WORD = rf"""(?:{PLAIN}|{VARIABLE_WORD}|'{PLAIN_QUOTED}*'|"{PLAIN_QUOTED}*")+"""
TOKEN = rf"(?:\d*>&\d+|(?:&|\d*)>>?[ \t]*{WORD}|<[ \t]*{WORD}|{WORD})"
PROGRAM = rf"[ \t]*{TOKEN}(?:[ \t]+{TOKEN})*[ \t]*"
ALONE = re.compile(PROGRAM)
CHAIN = re.compile(rf"{PROGRAM}(?:&&{PROGRAM})*")  # ends with 0 only when every program did

# The one shape of a command whose programs can be read (`plain`): the words above, an escaped parenthesis, and as
# the only expansions a variable's value, quoted or not, joined by the operators. Nothing in it runs a program.
VALUE = r"\$(?:[A-Za-z_][A-Za-z0-9_]*|\{[A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])?\}|\?|\{\?\})"
PLAIN_WORD = rf"""(?:{PLAIN}|\\[()]|{VALUE}|'{PLAIN_QUOTED}*'|"(?:{PLAIN_QUOTED}|{VALUE})*")+"""
PLAIN_TOKEN = rf"(?:\d*>&\d+|(?:&|\d*)>>?[ \t]*{PLAIN_WORD}|<[ \t]*{PLAIN_WORD}|{PLAIN_WORD})"
PLAIN_PROGRAM = rf"[ \t]*{PLAIN_TOKEN}(?:[ \t]+{PLAIN_TOKEN})*[ \t]*"
PLAIN_COMMAND = re.compile(rf"{PLAIN_PROGRAM}(?:(?:&&|\|\||[;|]){PLAIN_PROGRAM})*")
# Programs that always hand the shell on to what follows them: never `exit`, `exec`, `set` or `source`, nor a
# wrapper that runs another program (`env`, `timeout`, `xargs`), nor a program by its path, which may be anything.
CONTINUES = frozenset((
    "awk", "basename", "cat", "cd", "cmp", "cp", "cut", "diff", "dirname", "du", "echo", "false", "file", "find", "go",
    "grep", "head", "ls", "md5sum", "mkdir", "mv", "nl", "node", "printf", "pwd", "python", "python3", "readlink",
    "realpath", "rm", "sed", "sha256sum", "sort", "stat", "tail", "test", "touch", "tr", "tree", "true", "uniq",
    "wc"))


def plain(command):
    """Whether `command` has the one shape whose programs can be read (the module's docstring)."""
    return bool(PLAIN_COMMAND.fullmatch(command))


def continues(text):
    """Whether the program `text`, to the operator after it, hands the shell on (the module's docstring)."""
    rest = text.strip(" \t") + " "
    rest = rest[ASSIGNMENT.match(rest).end():].split(None, 1)
    return not rest or rest[0] in CONTINUES


def _owns_exit_code(command, code):
    """Whether `command` ending with `code` means its own program ended with it (the module's docstring)."""
    return bool((CHAIN if code == 0 else ALONE).fullmatch(command)) and all(
        continues(text) for _, text in parts(command)[:-1])


def parts(command):
    """[(operator before it, text)] of each top-level program of `command` (the module's docstring)."""
    starts = _starts(command)
    ends = [where for _, where, _ in starts[1:]] + [len(command)]
    return [(operator, command[start:end]) for (operator, _, start), end in zip(starts, ends)]


def exit_code(command, program, code, output):
    """The exit code of program `program` of `command`, or None when it cannot be known (the module's docstring)."""
    found = parts(command)
    if code is None or "\n" in command or not 0 <= program < len(found):
        return None  # a command whose own code nobody saw may have stopped before any echo of a code ran
    units = []  # [program numbers] of each unit: a program after the start or a `;`, and what is joined to it
    for n, (op, _) in enumerate(found):
        units.append([n]) if op in ("", ";") else units[-1].append(n)
    if not all(continues(found[n][1]) for n in range(program)):
        return None  # an earlier program may have ended the shell, so this one may never have run
    at = next(n for n, unit in enumerate(units) if program in unit)
    if any(found[n][0] != "&&" for n in units[at][1:]):
        return None  # `_owns_exit_code` below then holds for a nonzero code only when the program is alone
    if at == len(units) - 1:  # the last unit of a list of plain units gives the command's code
        known = code if all(CHAIN.fullmatch(_joined(found, u)) for u in units) else None
    else:
        known = _echoed(found, units, at + 1, output)
    return known if known is not None and _owns_exit_code(_joined(found, units[at]), known) else None


def _joined(found, unit):
    return found[unit[0]][1] + "".join(found[n][0] + found[n][1] for n in unit[1:])


ECHOED = re.compile(r"([^$]*)\$(\?|\{\?\}|[A-Za-z_][A-Za-z0-9_]*|\{[^}\s]*\})")  # `echo <words>` and a value


def _echo(text):
    """(what `echo` prints before a value it ends with, that value), when `text` is an `echo` of words and one
    value at the end; ("", None) for any other `echo`; None when it is not an `echo` the shell's words split."""
    try:
        words = shlex.split(text)
    except ValueError:
        return None
    if words[:1] != ["echo"]:
        return None
    said = ECHOED.fullmatch(" ".join(words[1:]))
    return said.groups() if said else (" ".join(words[1:]), None)


def _echoed(found, units, at, output):
    """The code that unit `at`, `echo <words>$?`, printed, or None (the module's docstring)."""
    echo = _echo(_joined(found, units[at])) if len(units[at]) == 1 else None
    if echo is None or echo[1] not in ("?", "{?}"):
        return None
    printers = []  # the units that may print a line of `echo[0]` and a number, in order
    for n, unit in enumerate(units):
        for program in unit:
            other = _echo(found[program][1])
            if other is not None and other[0].startswith(echo[0]):
                if len(unit) > 1 or other[1] is None or other[0] != echo[0]:
                    return None  # it may not run, or may print a line of that shape another way
                printers.append(n)
    lines = re.findall(rf"^{re.escape(echo[0])}(\d+)$", output or "", re.MULTILINE)
    return int(lines[printers.index(at)]) if len(lines) == len(printers) else None


def _starts(command):
    """[(operator, where it starts, where the program after it starts)] of `command`, the first with operator ""."""
    starts, quote, i = [("", 0, 0)], None, 0
    while "\n" not in command and i < len(command):  # a line break may begin a heredoc, so only the start counts
        char = command[i]
        if quote:
            quote = None if char == quote else quote
        elif char in "'\"":
            quote = char
        elif match := OPERATOR.match(command, i):
            starts.append((match.group(), i, match.end()))
            i = match.end()
            continue
        i += 1
    return starts


def programs(command):
    """The text from each place a program starts in `command` to its end."""
    return [text for text, _ in codes(command, None, None)]


def codes(command, code, output):
    """[(text, exit code or None)] of each program of `command`, which ended with `code` and printed `output`."""
    found = []
    for n, (_, _, start) in enumerate(_starts(command)):
        text = command[start:].lstrip(" \t")
        text = text[ASSIGNMENT.match(text).end():]
        own = exit_code(command, n, code, output)
        found.append((text, own))
        if script := SHELL_SCRIPT.match(text):
            found += codes(script.group(1)[1:-1], own, None)
    return found


def words(command):
    """[the words of each program of `command`, or None where they cannot be split], as the module's docstring says."""
    found = []
    for text in programs(command):
        if SHELL_SCRIPT.match(text):
            continue  # its script's programs follow, from `programs`
        own = text[:_starts(text)[1][1]] if len(_starts(text)) > 1 else text
        try:
            found.append(None if "\n" in own else shlex.split(own))
        except ValueError:
            found.append(None)
    return found


def _stateless(program):
    """Whether one program, as its text from its start to the next operator, changes no state of the shell."""
    text = program.strip(" \t")
    word = text[ASSIGNMENT.match(text).end():].split(None, 1)
    return bool(word) and "=" not in word[0] and ("/" in word[0] or word[0] in STATELESS)


def cut(command, drop):
    """`command` without each pipeline whose text `drop` takes, as the module says; "" when nothing is left, and
    None when the command cannot be cut cleanly."""
    if not CUTTABLE.fullmatch(command):
        return None
    starts = _starts(command)
    ends = [where for _, where, _ in starts[1:]] + [len(command)]
    units = []  # [operator before it, text, its programs]: a pipeline, split at each && || and ;
    for (operator, _, start), end in zip(starts, ends):
        if operator == "|":
            units[-1][1] += "|" + command[start:end]
            units[-1][2].append(command[start:end])
        else:
            units.append([operator, command[start:end], [command[start:end]]])
    kept, gone, blank = [], False, ""  # blank: the blanks before a pipeline's operator, as its own text ends
    for operator, text, parts in units:
        # what depends on a removed pipeline goes with it: it reads its $?, or && or || join it, down the chain
        gone = drop(text) or (gone and (operator in ("&&", "||") or "$?" in text))
        if gone and not all(_stateless(part) for part in parts):
            return None
        if not gone:
            kept.append((blank + operator, text.rstrip(" \t")))
        blank = text[len(text.rstrip(" \t")):]
    if not kept:
        return ""
    lead = command[:len(command) - len(command.lstrip(" \t"))]
    return lead + kept[0][1].lstrip(" \t") + "".join(join + text for join, text in kept[1:]) + blank
