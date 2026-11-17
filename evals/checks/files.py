"""Checks of the world's files after a run, read from the files after and the world diff, which the harness itself
made: never from what the host said it did.

- `file_state`: the file at `path` exists, is absent, is unchanged, or was changed or added by the run.
- `changes_only_in`: every path the run changed matches one of the globs in `allowed` (`*` crosses folders). A
  folder added or removed is allowed too when it holds only allowed changes, so `.harness` may be made to hold
  `.harness/*`; a file replaced by a folder, or an empty folder, is a change like any other.
- `lists_every_change`: the file at `file`, written by the run, names by its own whole path every file the run added
  or changed, `file` itself and the run's own `.harness/` files left out. A path is named only between allowed
  bounds: before it the text's start, a space, or one of `` ` ( [ " ' < | ``; after it the text's end, a space, one
  of `` ` ) ] " ' > | , ; : ``, or a full stop that ends a sentence. A path in `*` emphasis is named too. So a
  folder, a pattern such as `path*`, or a count names none of the files in it.
"""

import re

from cases import is_path  # the one shape of a world path, as cases and the lint use it
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


BEFORE = r"(?:^|(?<=[\s`(\[\"'<|]))"  # the only bounds a named path may have, an allow list (HW-AG-09)
AFTER = r"(?=$|[\s`)\]\"'>|,;:]|\.(?:\s|$))"


def lists_every_change(bundle, file):
    text = bundle.text(file)
    if text is None or file not in bundle.changes:
        return "fail", f"{file} is not a file the run wrote"
    written = sorted(path for path in bundle.changes if path != file and not path.startswith(".harness/")
                     and bundle.text(path) is not None)
    missing = [path for path in written
               if not re.search(f"{BEFORE}{re.escape(path)}{AFTER}|(?<=\\*){re.escape(path)}(?=\\*)", text)]
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
