"""Where the programs of a shell command start: the one splitter the command checks (`evals/checks/commands.py`) and
the grader view (`view.py`) share, so the two never disagree on it.

- `programs(command)`: the text from each place a program starts to the command's end. A program starts at the
  start of the command, after an operator outside quotes (`&&`, `||`, `;`, `|`), after any `NAME=value` words, and
  the same way inside the script of a shell's `-c` flag. A command with a line break is read only from its start,
  since a later line may be a heredoc's text.
- `cut(command, drop)`: the command without each of its pipelines that `drop` takes, or None when no clean cut is
  possible. A cut leaves only what an agent could have typed: a removed pipeline takes the operator before it with
  it (after it, for the first), and the pipelines right after it that read its exit code (`$?`). A command is cut
  only when it has one shape (`CUTTABLE`), in which the splitter's reading of quotes is exact, and every program it
  removes leaves the shell as it found it (`STATELESS`), so no later program reads a folder, a variable or an
  output it set.

Standard library only.
"""

import re

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
    "grep", "head", "ls", "md5sum", "mkdir", "mv", "nl", "node", "printf", "python", "python3", "readlink",
    "realpath", "rm", "sed", "sha256sum", "sort", "stat", "tail", "test", "time", "timeout", "touch", "tr", "tree",
    "uniq", "wc", "xargs"))


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
        gone = drop(text) or (gone and "$?" in text)  # what reads the code of a removed pipeline goes with it
        if gone and not all(_stateless(part) for part in parts):
            return None
        if not gone:
            kept.append((blank + operator, text.rstrip(" \t")))
        blank = text[len(text.rstrip(" \t")):]
    if not kept:
        return ""
    lead = command[:len(command) - len(command.lstrip(" \t"))]
    return lead + kept[0][1].lstrip(" \t") + "".join(join + text for join, text in kept[1:]) + blank
