"""Evidence: one host-neutral record of every run (doc 11, Evidence).

One rule: a run's output is read once into manifests (`manifest.py`) and leaves only through one scrub
(`scrub.py`), which runs on what the run made (its files, paths, link targets, log and transcript) and never on what
the harness made (hashes, fields, the case), so a short credential can never change a hash or a field. In the action
log, a value the harness chose (`host.FIXED`: an entry's kind, its source, a write's hash) is kept when it passes its
test, and every other value is the run's. `collect` reads the world after the run once, diffs it against the proved
arm, and scrubs the whole record and every file before anything is kept. Home and scratch are scanned for canaries
in every name, link target and file, and anything the scan cannot read refuses the run. `store` writes a bundle as
`bundle.json`, the scrubbed record, and `blobs/<sha256>`, each file's scrubbed bytes named by their own hash. So no
name the run chose ever touches the disk, names cannot collide on disk, and nothing in a bundle is a link. Every
check and grader reads only the bundle.

The record's fields are the ones `collect` writes, as doc 11 lists them. The world diff leaves out the host's own
files (those paths only) and both copies of the installed skill with the folders above them, the same in both arms.
A pipe, socket or device the agent made is an `other` entry. `.git` is not read: the agent's git commands are logged.

Standard library only.
"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath

import host
import manifest
import scrub as scrubs
import world as worlds
from cases import REPO

SKIP = (".git",)
REQUEST_LIMIT = 200  # characters of a gate request line a bundle keeps, cut after the scrub


class EvidenceError(RuntimeError):
    """A bundle cannot be made or stored as this module says. The round stops."""


def overlay(case, adapter, skills_root=None, skill_dir=None):
    """What the with-skill arm of `case` adds to the without-skill arm: the skill, the paths it is installed at (its
    declared folder and the host's discovery copy), its index file and row, and the index file's entry in the
    without-skill arm (all three None without an index)."""
    skill = worlds.plan(case, adapter, True, skills_root, skill_dir)[-1]  # the plan installs the skill last
    index = case.index["file"] if case.index else None
    without = worlds.expected(case, worlds.plan(case, adapter, False, skills_root, skill_dir))[0]
    return {"skill": skill.name, "paths": list(skill.targets), "index": index, "row": skill.row,
            "index_without": without.get(index) if index else None}


def own_files(drift, mode):
    """The world paths the host writes for itself in `mode`, from a tools and drift record (`probes.drift`)."""
    return sorted(path[len("world/"):] for path in drift["own files"][mode] if path.startswith("world/"))


def covers(places, path, before=None, after=None):
    """Whether a change of `path` from the entry `before` to `after` is left out for `places`: the path is one of
    them or lies under one, or it is a folder above one, which only holds it (both entries a folder or none)."""
    mine = {str(p) for p in PurePosixPath(path).parents}
    holder = before in ("dir", None) and after in ("dir", None)
    return any(path == place or place in mine or (holder and path in {str(p) for p in PurePosixPath(place).parents})
               for place in places)


def diff(before, after, leave_out=(), exact=()):
    """{path: {"before": entry or None, "after": entry or None}} for every path whose entry differs between two
    manifests, except the paths `leave_out` covers (`covers`) and the paths in `exact` themselves."""
    return {path: {"before": before.get(path), "after": after.get(path)}
            for path in sorted(set(before) | set(after))
            if before.get(path) != after.get(path) and path not in exact
            and not covers(leave_out, path, before.get(path), after.get(path))}


def collect(contained, result, case, arm, overlay, drift, host_version, model):
    """The scrubbed record and blobs of one run, after it ran: `result` is what `host.run` returned for `contained`,
    `arm` is `with_skill` or `without_skill`, `overlay` is the case's `overlay` and `drift` the host's tools and drift
    record. The run's scrub is made here, after the run, so a credential the host refreshed is known. Raise
    `scrub.Leak` when a canary token reached the run's output, which voids it, and `EvidenceError` when the world
    cannot be read. A command's output is kept whole."""
    scrub = scrubs.Scrub.of_run(contained, overlay)
    for label, folder in (("home", contained.home), ("scratch", contained.scratch)):
        _scan(folder, label, scrub)  # what the host kept for itself, such as a session file, is scanned too
    try:
        after = manifest.manifest(contained.world, skip=SKIP, other=True)  # a pipe the agent made is part of it
    except manifest.Unreadable as error:
        raise EvidenceError(scrub.quiet(f"the world after the run cannot be read: {error}")) from None
    before = {p: e for p, e in contained.world_entries.items() if p.split("/")[0] not in SKIP}
    blobs, stored = {}, {}
    for path, entry in after.items():
        if manifest.is_file(entry):
            data = scrub.blob((contained.world / path).read_bytes(), f"world/{path}")
            digest = hashlib.sha256(data).hexdigest()
            blobs[digest] = data
            entry = f"file {digest}" + entry[len("file ") + 64:]  # the executable bit is kept
        elif manifest.kind(entry) == "link":
            entry = "link " + scrub.text(entry[len("link "):], f"world/{path}")
        stored[path] = entry
    own = own_files(drift, contained.mode)
    changes = diff(before, after, overlay["paths"], own)
    for path, change in changes.items():
        if change["after"] is not None:
            change["after"] = stored[path]  # the before entry is the arm's own, as the proof recorded it
    transcript = {}
    for name, text in (("stdout", result.stdout), ("stderr", result.stderr)):
        data = scrub.text(text, f"the host's {name}", neutral=True).encode(errors="surrogateescape")
        transcript[name] = hashlib.sha256(data).hexdigest()
        blobs[transcript[name]] = data
    messages = [item["text"] for item in result.log if item["kind"] == "message"]
    ran = scrub.value({"failure": result.failure, "exposure": result.exposure,  # what the run reported
                       "final_message": messages[-1] if messages else None, "requests": result.requests}, "bundle")
    ran["log"] = scrubbed_log(scrub, result.log, "bundle/log")
    record = {"case": case.id, "arm": arm, "mode": contained.mode, "host": contained.adapter.NAME,  # the harness's
              "host_version": host_version, "model": model, "seconds": result.seconds, "overlay": overlay,
              "own_files": own, "folders": scrubs.folders(contained),
              "transcript": transcript, "files_after": scrub.names(stored, "bundle/files_after"),
              "diff": scrub.names(changes, "bundle/diff"), **ran}
    for item in record["requests"]:
        item["request"] = item["request"][:REQUEST_LIMIT]
    return record, blobs


def scrubbed_log(scrub, log, where):
    """An action log as a record may keep it: each value through `scrub`, but a value the harness chose."""
    return [{name: value if name in host.FIXED and host.FIXED[name](value)
             else scrub.value(value, f"{where}/{number}/{name}") for name, value in item.items()}
            for number, item in enumerate(log)]


def _scan(folder, label, scrub):
    if folder is None:
        return
    def unread(error):  # what the scan cannot read could hold anything, so the run's evidence is refused
        where = os.path.relpath(error.filename, folder) if error.filename else "a path"
        raise EvidenceError(f"cannot scan {label}/{scrub.quiet(where)}") from None
    for root, dirs, names in os.walk(folder, onerror=unread):
        for path in (Path(root) / name for name in dirs + names):  # a link's target is scanned, never followed
            where = f"{label}/{path.relative_to(folder)}"
            scrub.check(where, where)  # a name the run chose is output too
            try:
                data = os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else ""
            except OSError as error:
                unread(error)
            scrub.check(data, where)


def store(record, blobs, out):
    """Write one bundle to the new folder `out`, outside the repository, and read every blob back by its hash."""
    out = Path(out).resolve()
    if out.is_relative_to(REPO.resolve()):
        raise EvidenceError(f"a bundle is stored outside the repository, not in {out}")
    if out.exists():
        raise EvidenceError(f"{out} already exists: a bundle is written to a new folder")
    if _named(record) != set(blobs):
        raise EvidenceError("the record and its blobs do not name the same files")
    (out / "blobs").mkdir(parents=True)
    for digest, data in blobs.items():
        (out / "blobs" / digest).write_bytes(data)
    (out / "bundle.json").write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
    load(out)
    return out


def _named(record):
    """The blobs a record names: each file after, and the transcript."""
    files = {entry.split(" ")[1] for entry in record["files_after"].values() if manifest.is_file(entry)}
    return files | set(record["transcript"].values())


def load(out):
    """The record of the bundle in `out`, and a function that gives a blob's bytes by hash. Raise EvidenceError when
    a blob is missing or its bytes do not have its hash."""
    out = Path(out)
    record = json.loads((out / "bundle.json").read_text())

    def blob(digest):
        data = (out / "blobs" / digest).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise EvidenceError(f"blob {digest} does not have its hash")
        return data

    named = _named(record)
    if set(os.listdir(out / "blobs")) != named:
        raise EvidenceError(f"{out}: the blobs are not exactly the ones the record names")
    for digest in named:
        blob(digest)
    return record, blob
