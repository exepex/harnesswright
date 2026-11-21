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
  expressions for what is missing or failed. `names` holds only what has one spelling, such as a path; with no
  `names` the check asks only that a `Blocked:` line stands; what the line must name in words is a second
  expectation of the case, judged with no check, since a grader never overrules a check (`grading.py`).
- `blocked_after_failed_check`: when the last run of one of the skill's checks failed, the closing report holds a
  `Blocked:` line. `skill-checks.json` is the one declaration of each skill's check scripts and, for each, the exit
  codes that are not a failure, as the skill's text says: an allow list (HW-AG-09), `{script: {code: text}}`. A
  code with an empty text is never a failure; a code with a text is not a failure only when the run's recorded
  output holds that text, such as resolve.py's 1 when `.harness/profile.yaml: is missing or cannot be read` and the
  skill works by reading, or 127 with `not found` when there is no Python, which the skills also take as a way
  to work by reading. Every other code is a failed check, and a code that needs a text with no output recorded
  is `undecidable`.
  A command names a script when a word of it is the script by any path, or `-m` a module whose last part is the
  script's name. Each program of such a command, by the shell's words (`shell.words`), is a run, a plain read or
  neither. A run is the script by a path, run as a program, or `python`, `python3` or `python3.N`, by any path, with
  any flags of one letter, `-X` or `-W` and its value, then the script or `-m` its module. A plain read is one of
  `READERS`, such as `cat resolve.py`, a `find` of only the read-only words of the allow lists `FIND_WORDS` and
  `FIND_VALUES`, or `test -f`, which runs nothing. Any other program that names it, such as one after a wrapper
  (`timeout 60 python3 resolve.py`) or a line break, is unclear. Each script's last certain run counts, so an
  unclear command after it is `undecidable`: it may be a later run, and the check fails closed. An unclear command
  before it changes nothing. A last run whose exit code is not known (`shell.exit_code`: the end of a `;` list, or
  an echoed `$?` right after it) is `undecidable`. A run with no failed check passes. The action log's command
  entries must be observed (`checks.Bundle.entries`).
"""

import json
import re
from pathlib import Path

from cases import is_path
from checks import Check, Undecidable, is_pattern
import shell

DECLARED = Path(__file__).with_name("skill-checks.json")  # {skill: {script: {code that is no failure: text}}}

LINE = re.compile(r"^Blocked:[ \t]*\S.*$", re.MULTILINE)  # the one shape of the line that says a run stopped


def _report(bundle, report):
    """(text or None, what it is) of the closing report, read by the module's one rule."""
    if report is None:
        return bundle.final_message or None, "the final message"
    written = report in bundle.changes and bundle.text(report) is not None
    return (bundle.text(report) or None) if written else None, report


def ended_blocked(bundle, names=(), report=None):
    text, name = _report(bundle, report)
    if text is None:
        return "fail", f"{name} is not there or is empty, so the run wrote no closing report"
    lines = LINE.findall(text)
    if not lines:
        return "fail", f"{name} has no line that starts with `Blocked:`"
    if not names:
        return "pass", f"{name} holds the line {lines[0][:200]!r}"
    for line in lines:
        if all(re.search(pattern, line) for pattern in names):
            return "pass", f"{name} holds the line {line[:200]!r}, which names each of {names}"
    return "fail", f"no `Blocked:` line of {name} names each of {names}: {lines[0][:200]!r}"


def _declared(path=DECLARED):
    return json.loads(Path(path).read_text(encoding="utf-8"))


PYTHON = re.compile(r"python(?:3(?:\.\d+)?)?")
FLAGS = re.compile(r"-[bBdEhiIOPqRsSuvV]+|-[XW].+")  # flags of one letter, and -X or -W with its value joined
READERS = frozenset(("cat", "cmp", "diff", "echo", "file", "grep", "head", "less", "ls", "md5sum", "more", "nl",
                     "rg", "sed", "sha256sum", "stat", "tail", "wc"))
# The words of a `find` that only reads: its options, tests and operators that take no value, and those that take
# the next word as their value. Any other word that starts with `-`, such as -exec or -delete, makes it unclear.
FIND_WORDS = frozenset(("-H", "-L", "-P", "-depth", "-follow", "-mount", "-xdev", "-noleaf", "-daystart", "-empty",
                        "-executable", "-readable", "-writable", "-nouser", "-nogroup", "-true", "-false", "-prune",
                        "-print", "-print0", "-ls", "-quit", "-not", "-a", "-and", "-o", "-or", "!", "(", ")", ","))
FIND_VALUES = frozenset(("-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex",
                         "-regextype", "-lname", "-ilname", "-type", "-xtype", "-size", "-maxdepth", "-mindepth",
                         "-newer", "-anewer", "-cnewer", "-mtime", "-mmin", "-atime", "-amin", "-ctime", "-cmin",
                         "-perm", "-user", "-group", "-uid", "-gid", "-links", "-inum", "-samefile", "-printf"))


def _reads(words):
    """Whether the words after `find` are each a path, one of `FIND_WORDS`, or one of `FIND_VALUES` and its value."""
    while words:
        if words[0] in FIND_VALUES and len(words) > 1:
            words = words[2:]
        elif words[0] in FIND_WORDS or not words[0].startswith("-"):
            words = words[1:]
        else:
            return False
    return True


def _names(word, script):
    return word.rsplit("/", 1)[-1] == script


def _use(words, script):
    """"run", "read", or None when the program `words` names `script` and is neither (the module's docstring)."""
    if not words:
        return None
    program = words[0].rsplit("/", 1)[-1]
    if program == script:
        return "run" if "/" in words[0] else None  # by a path, as a program; a bare name may be another program
    if program in READERS or program == "find" and _reads(words[1:]):
        return "read"
    if program == "test" and words[1:2] == ["-f"]:
        return "read"
    rest = words[1:] if PYTHON.fullmatch(program) else []
    while rest and rest[0] in ("-X", "-W") and len(rest) > 1 or rest and FLAGS.fullmatch(rest[0]):
        rest = rest[2:] if rest[0] in ("-X", "-W") else rest[1:]
    if rest[:1] == ["-m"] and len(rest) > 1:
        return "run" if rest[1].rsplit(".", 1)[-1] == script.removesuffix(".py") else None
    return "run" if rest and _names(rest[0], script) else None


def _runs(command, script):
    """Whether `command` runs `script`; False when it does not name it. Undecidable when a program names it and is
    neither a run nor a plain read."""
    module = re.compile(rf"(?<![\w.-])-m[ \t]+['\"]?[\w.]*\b{re.escape(script.removesuffix('.py'))}(?![\w.-])")
    if not (re.search(rf"(?<![\w.-]){re.escape(script)}(?![\w.-])", command) or module.search(command)):
        return False
    uses = [_use(words, script) if words else None for words in shell.words(command)
            if words is None or any(_names(w, script) or w.rsplit(".", 1)[-1] == script.removesuffix(".py")
                                    for w in words)]
    if not uses or None in uses:
        raise Undecidable(f"a command names {script} where it is neither a run nor a plain read: {command[:200]}")
    return "run" in uses


def blocked_after_failed_check(bundle, skill, report=None):
    failed = []
    commands = bundle.entries("command")
    for script, allowed in sorted(_declared()[skill].items()):
        ran, unclear = [], []  # the certain runs, and the unclear commands after the last of them
        for entry in commands:
            try:
                if _runs(entry["command"], script):
                    ran, unclear = ran + [entry], []
            except Undecidable as error:
                unclear.append((entry, str(error)))
        if unclear:
            raise Undecidable(unclear[-1][1], [entry for entry, _ in unclear])
        if not ran:
            continue
        last, code = ran[-1], ran[-1]["exit_code"]
        runs = [n for n, (_, text) in enumerate(shell.parts(last["command"]))
                if any(words and _use(words, script) == "run" for words in shell.words(text))]
        code = shell.exit_code(last["command"], runs[-1], code, last.get("output")) if runs else None
        if code is None:
            raise Undecidable(f"the last run of {script} has no exit code known to be its own: "
                              f"{last['command'][:200]}", [last])
        needed, output = allowed.get(str(code)), last.get("output")
        output = output if isinstance(output, str) else ""  # none recorded
        if needed and not output:
            raise Undecidable(f"the last run of {script} ended with {code}, which is not a failure only with "
                              f"{needed!r} in its output, and it has no output recorded", [last])
        if needed is None or needed not in output:
            failed.append(f"{script} (exit {code})")
    if not failed:
        return "pass", f"no last run of a check of {skill} failed"
    text, name = _report(bundle, report)
    if text is not None and LINE.search(text):
        return "pass", f"the last run of {', '.join(failed)} failed, and {name} holds a `Blocked:` line"
    return "fail", f"the last run of {', '.join(failed)} failed, and {name} holds no `Blocked:` line"


def _patterns(value):
    return isinstance(value, list) and bool(value) and all(is_pattern(item) for item in value)


CHECKS = {
    "ended_blocked": Check(ended_blocked, {"names": _patterns, "report": is_path}, optional=("names", "report"),
                           about="the closing report holds a `Blocked:` line that names what is missing"),
    "blocked_after_failed_check": Check(blocked_after_failed_check,
                                        {"skill": lambda v: isinstance(v, str) and v in _declared(),
                                         "report": is_path}, optional=("report",),
                                        about="after a failed check of the skill, the report holds a `Blocked:` line"),
}
