"""What a grader view shows of what the harness added: read by one rule for the view fault
(`grading_faults.view_`), on the clean record and on the planted one alike.

One rule. A page may show everything the run wrote and said, and nothing the harness put there (`view.ADDED`). So
it may hold no text that only the harness writes (a lead line, a run's real folder: `words`), no entry of the
overlay's files, and no arm word outside a world file both arms hold byte for byte, in a world file the run left as
built: such text cannot tell the arms apart. An internal world keeps docs 11 and 12 (doc 12, Internal worlds), which
name the arms; a grader reads the same text in every arm. That a file is held by both arms is proven, never assumed:
both arms of the case are built and a file is allowed only when its entry is the record's in each (`built`,
`shared`). The skill's name and paths are the run's words wherever it wrote them, and count nowhere. The tests are
written here, not taken from the view, so a fault in the view cannot hide itself.

Standard library only.
"""

import json
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


def shown(case, record, blob, words, held=None):
    """What the view of `record` (its record and every blob) or its page shows of what the harness added: each of
    `words` it holds, each path of its files and changes that is an overlay path or lies under one, and each arm
    word outside a file of `held` (`shared`) that `record` still holds unchanged."""
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
    places = [*record["overlay"]["paths"], *record["overlay"].get("release", [])]
    paths = [path for path in sorted({*found["files_after"], *found["diff"]})
             if any(path == place or path.startswith(place + "/") for place in places)]
    return [word for word in words if word in text] + paths + [arm for arm in (*cases.ARMS, cases.PREVIOUS)
                                                               if arm in arm_text]
