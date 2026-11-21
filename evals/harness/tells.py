"""What a grader view tells of its run's arm: the names a view or its page holds, read by one rule for the view
fault (`grading_faults.view_`), on the clean record and on the planted one alike.

One rule. Text that both arms hold byte for byte, in a world file the run left as built, cannot tell the arms
apart, so the arm words (`cases.ARMS`, `cases.PREVIOUS`) are read everywhere except in those files. An internal
world keeps docs 11 and 12 (doc 12, Internal worlds), which name the arms; a grader reads the same text in every
arm. That a file is held by both arms is proven, never assumed: both arms of the case are built and a file is
allowed only when its entry is the record's in each (`built`, `shared`). The skill's name and paths count everywhere,
in any spelling: whole, or inside a longer name such as `rules-text-<skill>.core.md`, a file only the with-skill arm
writes.

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


def built(case, adapter, folder):
    """The manifest of each arm of `case` as built, without and with the skill. `folder` makes a new empty folder,
    which this removes."""
    found = []
    for with_skill in (False, True):
        out = folder()
        try:
            found.append(manifest.manifest(world.build(case, adapter, out / "world", with_skill=with_skill).path))
        finally:
            shutil.rmtree(out, ignore_errors=True)
    return found


def shared(arms, record):
    """{path: entry} of the world files of `record` that both arms hold byte for byte as built (`arms`, from `built`)
    and the run left as they were: outside the record's diff, with the record's digest in each built arm."""
    digest = lambda entry: entry.split(" ")[1] if entry and manifest.is_file(entry) else None
    return {path: entry for path, entry in record["files_after"].items() if path not in record["diff"]
            and digest(entry) and all(digest(arm.get(path)) == digest(entry) for arm in arms)}


def shown(case, record, blob, names, held=None):
    """The names that the view of `record` (its record and every blob) or its page holds, each by the rule the view
    keeps for it. The skill's name and paths count wherever no ASCII letter or digit stands next to them, so inside
    a longer name such as `rules-text-<skill>.core.md` too, as the view hides them. An arm's name counts anywhere
    except in a file of `held` (`shared`) that `record` still holds unchanged. The tests are written here, not taken
    from `view.spelled`, so a fault in that pattern cannot hide itself."""
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
    return [name for name in names if re.search(f"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text)] \
        + [arm for arm in (*cases.ARMS, cases.PREVIOUS) if arm in arm_text]


def clean(case, pages, arms, named):
    """([(page, held)], told): the pages (`grading_faults._pages`) whose clean view names nothing a plant would,
    each with the files both built `arms` hold (`shared`), and what a clean view tells that it never may: the
    skill's name, or an arm's outside those files. `named` gives the names of a record's overlay. A clean view that
    names only a path of the overlay, as the world itself holds one (a release file such as `rules/core/work.md`
    under `v2/`), is no page for a plant, which could prove nothing there, and no fault of the view."""
    found = []
    for page in pages:
        held = shared(arms, page[1])
        shown_ = shown(case, page[1], page[2], named(page[1]["overlay"]), held)
        told = [name for name in shown_ if name in (page[1]["overlay"]["skill"], *cases.ARMS, cases.PREVIOUS)]
        if told:
            return [], told
        if not shown_:
            found.append((page, held))
    return found, []
