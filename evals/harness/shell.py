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
- `owns_exit_code(command, code)`: whether the command's exit code, when it is `code`, is its own program's. That
  holds for one program with its arguments, each a plain word, a simple quoted string of a plain word's characters
  and blanks, or a redirect such as `2>&1`; and, for code 0 only, for such programs joined by `&&`, which ends with 0
  only when each did. Any other shape, such as a pipe, `||`, `;` or `$(`, may end with another program's code. A
  plain word may hold a variable such as `$S`, which changes no exit code.
- `exit_code(command, program, code, output)`: the exit code of the top-level program numbered `program` (from 0,
  as `parts` counts them) of a command that ended with `code` and printed `output`, or None when it cannot be known.
  One rule, two ways to know it. In a list of plain programs joined only by `;` (no `&&`, `||` or pipe), the last
  program owns the command's code, so it is `code` when `program` is the last; a command of one program owns it as
  `owns_exit_code` says. And when `program` is a plain program, first or after a `;`, and the program right after
  it, after a `;`, is `echo` of a text ending in `$?` and holding no other `$`, the code is the number after that
  text on the one line of `output` that is the text with its number.
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


def owns_exit_code(command, code):
    """Whether `command` ending with `code` means its own program ended with it (the module's docstring)."""
    return bool((CHAIN if code == 0 else ALONE).fullmatch(command))


def parts(command):
    """[(operator before it, text)] of each top-level program of `command` (the module's docstring)."""
    starts = _starts(command)
    ends = [where for _, where, _ in starts[1:]] + [len(command)]
    return [(operator, command[start:end]) for (operator, _, start), end in zip(starts, ends)]


def exit_code(command, program, code, output):
    """The exit code of program `program` of `command`, or None when it cannot be known (the module's docstring)."""
    found = parts(command)
    if "\n" in command or not 0 <= program < len(found):
        return None
    if program == len(found) - 1:
        if len(found) == 1:
            return code if code is not None and owns_exit_code(command, code) else None
        listed = all(op in ("", ";") and ALONE.fullmatch(text) for op, text in found)
        return code if listed else None
    op, text = found[program]
    after_op, after = found[program + 1]
    if op not in ("", ";") or after_op != ";" or not ALONE.fullmatch(text):
        return None
    try:
        words = shlex.split(after)
    except ValueError:
        return None
    said = " ".join(words[1:])
    if words[:1] != ["echo"] or not said.endswith("$?") or "$" in said[:-2]:
        return None
    lines = re.findall(rf"^{re.escape(said[:-2])}(\d+)$", output or "", re.MULTILINE)
    return int(lines[0]) if len(lines) == 1 else None


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
    found = []
    for _, _, start in _starts(command):
        text = command[start:].lstrip(" \t")
        text = text[ASSIGNMENT.match(text).end():]
        found.append(text)
        if script := SHELL_SCRIPT.match(text):
            found += programs(script.group(1)[1:-1])
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
