"""Checks of the world's files after a run, read from the files after and the world diff, which the harness itself
made: never from what the host said it did.

- `file_state`: the file at `path` exists, is absent, is unchanged, or was changed or added by the run.
- `changes_only_in`: every path the run changed matches one of the globs in `allowed` (`*` crosses folders). A
  folder added or removed is allowed too when it holds only allowed changes, so `.harness` may be made to hold
  `.harness/*`; a file replaced by a folder, or an empty folder, is a change like any other.
"""

from cases import is_path  # the one shape of a world path, as cases and the lint use it
from checks import Check, matches

STATES = ("exists", "absent", "unchanged", "changed")


def is_globs(value):
    return isinstance(value, list) and bool(value) and all(isinstance(v, str) and v for v in value)


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


CHECKS = {
    "file_state": Check(file_state, {"path": is_path, "state": lambda v: v in STATES},
                        about="the file at a path exists, is absent, is unchanged, or was changed"),
    "changes_only_in": Check(changes_only_in, {"allowed": is_globs},
                             about="the run changed only paths matching the allowed globs"),
}
