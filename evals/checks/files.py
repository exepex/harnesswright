"""Checks of the world's files after a run, read from the files after and the world diff, which the harness itself
made: never from what the host said it did.

- `file_state`: the file at `path` exists, is absent, is unchanged, or was changed or added by the run.
- `changes_only_in`: every path the run changed matches one of the globs in `allowed` (`*` crosses folders). A
  folder added or removed is allowed too when it holds only allowed changes, so `.harness` may be made to hold
  `.harness/*`; a file replaced by a folder, or an empty folder, is a change like any other.
- `lists_every_change`: the file at `file`, written by the run, names by its own whole path every file the run added
  or changed, `file` itself and the run's own `.harness/runs/` files left out. One rule reads the names. Outside code
  spans, Markdown emphasis (a run of one to three `*` that opens before a non-space and closes after one) is read as
  the text it holds. The text is then cut into tokens, each a longest run of the world's path characters (letters,
  digits, `. _ + @ -`), `/` or `*`. A token names the path it equals once a leading `./` and trailing full stops are
  dropped. A token that holds a `*` is a pattern and names no file, nor does a folder or a count.
"""

import re

from cases import PATH_PART, is_path  # the one shape of a world path, as cases and the lint use it
from checks import Check, is_globs, matches

STATES = ("exists", "absent", "unchanged", "changed")


def file_state(bundle, path, state):
    is_file = bundle.text(path) is not None
    touched = path in bundle.changes
    holds = {"exists": is_file, "absent": path not in bundle.files, "unchanged": is_file and not touched,
             "changed": is_file and touched}[state]
    seen = ("changed by the run" if touched else "as it was") if is_file else (
        "absent" if path not in bundle.files else f"not a file: {bundle.files[path]}")
    return ("pass" if holds else "fail"), f"{path} is {seen}, and the expectation is {state}"


def changes_only_in(bundle, allowed):
    def holder(path, change):  # a folder added or removed only to hold allowed changes, such as `.harness` itself
        below = [other for other in bundle.changes if other.startswith(path + "/")]
        return ({change["before"], change["after"]} == {"dir", None} and bool(below)
                and all(matches(other, allowed) or bundle.changes[other]["before"] in ("dir", None)
                        and bundle.changes[other]["after"] in ("dir", None) for other in below))
    outside = [path for path, change in bundle.changes.items() if not matches(path, allowed)
               and not holder(path, change)]
    if outside:
        return "fail", f"the run changed paths outside {allowed}: {', '.join(outside[:20])}"
    return "pass", f"the run changed {len(bundle.changes)} paths, all inside {allowed}"


# The one shape a name may take, an allow list (HW-AG-09): the world's own path alphabet, `/` and `*`.
TOKEN = re.compile("[" + PATH_PART.pattern.removeprefix("[").removesuffix("-]+") + "/*-]+")
CODE = re.compile(r"(`+)(?:.|\n)*?\1")  # a code span holds no emphasis
EMPHASIS = re.compile(r"(\*{1,3})(?=\S)(.+?)(?<=\S)\1")


def _named(text):
    """The paths a text names, read by the module's one rule."""
    parts, at = [], 0
    for span in CODE.finditer(text):  # code spans as written, the prose between them with its emphasis read
        parts += [_unemphasised(text[at:span.start()]), span.group(0)]
        at = span.end()
    parts.append(_unemphasised(text[at:]))
    return {name for token in TOKEN.findall("\n".join(parts))
            if (name := token.rstrip(".").removeprefix("./")) and "*" not in name}


def _unemphasised(prose):
    while (read := EMPHASIS.sub(r"\2", prose)) != prose:
        prose = read
    return prose


def lists_every_change(bundle, file):
    text = bundle.text(file)
    if text is None or file not in bundle.changes:
        return "fail", f"{file} is not a file the run wrote"
    written = sorted(path for path in bundle.changes if path != file and not path.startswith(".harness/runs/")
                     and bundle.text(path) is not None)
    named = _named(text)
    missing = [path for path in written if path not in named]
    if missing:
        return "fail", f"{file} does not name {len(missing)} of the {len(written)} files the run wrote: " \
                       f"{', '.join(missing[:20])}"
    return "pass", f"{file} names each of the {len(written)} files the run wrote by its own path"


CHECKS = {
    "file_state": Check(file_state, {"path": is_path, "state": lambda v: v in STATES},
                        about="the file at a path exists, is absent, is unchanged, or was changed"),
    "changes_only_in": Check(changes_only_in, {"allowed": is_globs},
                             about="the run changed only paths matching the allowed globs"),
    "lists_every_change": Check(lists_every_change, {"file": is_path},
                                about="a file the run wrote names every file the run added or changed by its path"),
}
