"""Evidence: one host-neutral record of every run (doc 11, Evidence).

One rule: a run's output is read once into manifests (`manifest.py`) and leaves only through one scrub
(`scrub.py`). `collect` reads the world after the run once, diffs it against the proved arm, and scrubs the whole
record and every file before anything is kept. `store` writes a bundle as `bundle.json`, the scrubbed record, and
`blobs/<sha256>`, each file's scrubbed bytes named by their own hash. So no name the run chose ever touches the disk,
names cannot collide on disk, and nothing in a bundle is a link. Every check and grader reads only the bundle.

What the bundle holds: the case, the arm, the mode, the host, its version and model, the run's time, its failure (a
void run, or None), what the host exposed, the action log, the final message, the gate's requests, the overlay the
with-skill arm adds, the files after (the world's manifest, with each file's entry naming its stored blob), the
world diff, and the transcript: the host's stdout and stderr as blobs, with the skill neutralised.

The world diff leaves out the paths the host writes for itself, as the tools and drift probe measured them (those
paths only), and both copies of the installed skill, each with the folders above it, so both arms leave out the
same paths. A pipe, socket or device the agent left in the world is an `other` entry. `.git` is not read: what the agent did to the history is in its commands.

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


class EvidenceError(RuntimeError):
    """A bundle cannot be made or stored as this module says. The round stops."""


def overlay(case, adapter, skills_root=None, skill_dir=None):
    """What the with-skill arm of `case` adds to the without-skill arm: the skill, the paths it is installed at (its
    declared folder and the host's discovery copy), and its index file and row (both None without an index)."""
    skill = worlds.plan(case, adapter, True, skills_root, skill_dir)[-1]  # the plan installs the skill last
    return {"skill": skill.name, "paths": list(skill.targets),
            "index": case.index["file"] if case.index else None, "row": skill.row}


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
    cannot be read. A command's output is cut to `host.OUTPUT_LIMIT` only once the scrub has seen it whole."""
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
        stored[path] = entry
    changes = diff(before, after, overlay["paths"], own_files(drift, contained.mode))
    for path, change in changes.items():
        if change["after"] is not None:
            change["after"] = stored[path]  # the before entry is the arm's own, as the proof recorded it
    transcript = {}
    for name, text in (("stdout", result.stdout), ("stderr", result.stderr)):
        data = scrub.text(text, f"the host's {name}", neutral=True).encode(errors="surrogateescape")
        transcript[name] = hashlib.sha256(data).hexdigest()
        blobs[transcript[name]] = data
    messages = [item["text"] for item in result.log if item["kind"] == "message"]
    record = {
        "case": case.id, "arm": arm, "mode": contained.mode, "host": contained.adapter.NAME,
        "host_version": host_version, "model": model, "seconds": result.seconds, "failure": result.failure,
        "exposure": result.exposure, "log": result.log, "final_message": messages[-1] if messages else None,
        "requests": result.requests, "overlay": overlay, "files_after": stored, "diff": changes,
        "transcript": transcript,
    }
    record = scrub.value(record, "bundle")
    for item in record["log"]:
        if item["kind"] == "command":
            item["output"] = item["output"][:host.OUTPUT_LIMIT]
    return record, blobs


def _scan(folder, label, scrub):
    if folder is None:
        return
    for root, _, names in os.walk(folder):
        for name in names:
            path = Path(root) / name
            if path.is_file() and not path.is_symlink():
                scrub.check(path.read_bytes(), f"{label}/{path.relative_to(folder)}")


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
