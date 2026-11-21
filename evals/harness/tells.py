"""What a grader view tells of its run's arm: the names a view or its page holds, read by one rule for the view
fault (`grading_faults.view_`), on the clean record and on the planted one alike.

One rule. Text that both arms hold byte for byte, in a world file the run left as built, cannot tell the arms
apart, so the arm words (`cases.ARMS`, `cases.PREVIOUS`) are read everywhere except in those files. An internal
world keeps docs 11 and 12 (doc 12, Internal worlds), which name the arms; a grader reads the same text in every
arm. That a file is held by both arms is proven, never assumed: both arms of the case are built and a file is
allowed only when its entry is the record's in each (`shared`). The skill's name and paths count everywhere.

Standard library only.
"""

import json
import re
import shutil

import cases
import grading
import manifest
import view
import world


def seen(case, record, blob):
    """(view record, view blobs, page) of `record`."""
    found, blobs = view.view(record, blob)
    return found, blobs, grading.page(case.prompt, found, blobs)


def shared(case, adapter, folder, record):
    """{path: entry} of the world files of `record` that both arms of `case` hold byte for byte as built and the run
    left as they were: outside the record's diff, with the record's digest in the built world of each arm. `folder`
    makes a new empty folder, which this removes."""
    built = []
    for with_skill in (False, True):
        out = folder()
        try:
            built.append(manifest.manifest(world.build(case, adapter, out / "world", with_skill=with_skill).path))
        finally:
            shutil.rmtree(out, ignore_errors=True)
    digest = lambda entry: entry.split(" ")[1] if entry and manifest.is_file(entry) else None
    return {path: entry for path, entry in record["files_after"].items() if path not in record["diff"]
            and digest(entry) and all(digest(arm.get(path)) == digest(entry) for arm in built)}


def shown(case, record, blob, names, held=None):
    """The names that the view of `record` (its record and every blob) or its page holds, each by the rule the view
    keeps for it. The skill's name and paths count as whole names: not inside a longer name such as
    `rules-text-<skill>.core.md`, a file the run itself made. An arm's name counts anywhere except in a file of
    `held` (`shared`) that `record` still holds unchanged. The tests are written here, not taken from `world.names`,
    so a fault in that pattern cannot hide itself."""
    found, blobs, page = seen(case, record, blob)
    text = json.dumps(found, ensure_ascii=False) + "".join(data.decode("utf-8", "replace") for data in blobs.values())
    text += page
    kept = {path for path, entry in (held or {}).items()
            if path not in record["diff"] and record["files_after"].get(path) == entry}
    rest = {**found, "files_after": {p: e for p, e in found["files_after"].items() if p not in kept}}
    used = {e.split(" ")[1] for e in rest["files_after"].values() if manifest.is_file(e)}
    rest_blobs = {digest: data for digest, data in blobs.items() if digest in used}
    arm_text = json.dumps(rest, ensure_ascii=False) + "".join(
        data.decode("utf-8", "replace") for data in rest_blobs.values()) + grading.page(case.prompt, rest, rest_blobs)
    return [name for name in names if re.search(f"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])", text)] \
        + [arm for arm in (*cases.ARMS, cases.PREVIOUS) if arm in arm_text]
