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

`loaded` is the one reader of whether a run loaded its skill (doc 12, Proven use), from observed entries only.

Standard library only.
"""

import hashlib
import json
import os
import shlex
from pathlib import Path, PurePosixPath

import host
import manifest
import scrub as scrubs
import skills
import world as worlds
from cases import REPO

SKIP = (".git",)
REQUEST_LIMIT = 200  # characters of a gate request line a bundle keeps, cut after the scrub


class EvidenceError(RuntimeError):
    """A bundle cannot be made or stored as this module says. The round stops."""


def overlay(case, adapter, skills_root=None, skill_dir=None):
    """What the with-skill arm of `case` adds to the without-skill arm: the skill, the paths it is installed at (its
    declared folder and the host's discovery copy), every other file a team install adds (`release`, such as the
    release's run-time files), its index file and row, and the index file's entry in the without-skill arm (all
    three None without an index), and `edited`: each file the install edits in place, the index and a team
    profile (`world.edits`), with its entry in the without-skill arm. A skill with no folder yet adds nothing: its
    round runs without it only (`rounds.plan`, `absent`), and every reader of an overlay (runs, faults, goldens)
    takes it here."""
    known = skills.library(skills_root) if skills_root else skills.folders(REPO)
    if skill_dir is None and case.skill not in known:
        return {"skill": case.skill, "paths": [], "release": [], "index": None, "row": None, "index_without": None,
                "edited": {}}
    installs = worlds.plan(case, adapter, True, skills_root, skill_dir)
    skill = installs[-1]  # the plan installs the skill last
    index = case.index["file"] if case.index else None
    without = worlds.expected(case, worlds.plan(case, adapter, False, skills_root, skill_dir))[0]
    added, edited = worlds.expected(case, installs)
    release = sorted(path for path, entry in added.items() if path not in without and manifest.kind(entry) != "dir"
                     and not covers(skill.targets, path))
    return {"skill": skill.name, "paths": list(skill.targets), "release": release, "index": index, "row": skill.row,
            "index_without": without.get(index) if index else None,
            "edited": {path: without[path] for path in sorted(edited)}}


def places(overlay):
    """Every path the overlay covers, which no grader view shows: the skill's paths and the files a team install
    adds. An overlay stored before team installs has no `release`."""
    return [*overlay["paths"], *overlay.get("release", [])]


def loaded(record, skill, paths, text):
    """Whether the run `record` (a bundle's record) proves it loaded `skill`, installed at `paths` (the overlay's
    paths) with `text` its `SKILL.md` as installed. One allow list, of observed entries only: the host's own skill
    event naming it; a read of the exact `SKILL.md` of either installed copy; or a command one of whose own words is
    that `SKILL.md` and whose output holds the whole file. Nothing else proves a load: an inferred entry, such as a
    read an adapter parsed from a command, never does, nor a search whose output only mentions the skill."""
    world = next((path for path, word in record.get("folders", {}).items()
                  if word == scrubs.NEUTRAL_FOLDERS["world"]), None)
    files = {os.path.normpath(f"{path}/SKILL.md") for path in paths}
    whole = text.strip()

    def installed(path):  # a path in the world, as the overlay names it, or the path itself
        path = str(path)
        if world and path.startswith(world.rstrip("/") + "/"):
            path = path[len(world.rstrip("/")) + 1:]
        return os.path.normpath(path) in files

    for item in record["log"]:
        if not isinstance(item, dict) or item.get("source") != "observed":
            continue
        if item.get("kind") == "skill" and item.get("name") == skill:
            return True
        if item.get("kind") == "read" and installed(item.get("path", "")):
            return True
        if item.get("kind") == "command" and whole and whole in str(item.get("output", "")) \
                and any(installed(word) for word in _words(str(item.get("command", "")))):
            return True
    return False


def _words(command):
    """The words of a shell command, its operators apart; none when it cannot be split."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return []


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
    changes = diff(before, after, places(overlay), own)
    for path, change in changes.items():
        if change["after"] is not None:
            change["after"] = stored[path]  # the before entry is the arm's own, as the proof recorded it
    ran, texts = reported(contained, result, scrub, "bundle")
    transcript = {}
    for name, text in texts.items():
        data = text.encode(errors="surrogateescape")
        transcript[name] = hashlib.sha256(data).hexdigest()
        blobs[transcript[name]] = data
    record = {"case": case.id, "arm": arm, "mode": contained.mode, "host": contained.adapter.NAME,  # the harness's
              "host_version": host_version, "model": model, "seconds": result.seconds,
              "tokens": None if result.tokens is None else scrub.names(result.tokens, "bundle/tokens"),
              "overlay": overlay,
              "own_files": own, "folders": scrubs.folders(contained),
              "transcript": transcript, "files_after": scrub.names(stored, "bundle/files_after"),
              "diff": scrub.names(changes, "bundle/diff"), **ran}
    for item in record["requests"]:
        item["request"] = item["request"][:REQUEST_LIMIT]
    return record, blobs


def reported(contained, result, scrub, where="bundle"):
    """Everything a run made outside its world, by one rule: all of it passes `scrub`, the run's scrub
    (`scrub.Scrub.of_run`), made after the run and while its folders are there, so a credential the host refreshed is
    known. The folders the host kept for itself (home, scratch) are scanned for canaries; the transcript, the action
    log and every field of `result` (`host.run`) are scrubbed. Every run, task or grader, goes through here. Return
    the run's fields as a record keeps them ({"failure", "exposure", "final_message", "requests", "log"}) and the
    transcript texts ({"stdout", "stderr"}). Raise `scrub.Leak` when a canary reached any of it: the run is void."""
    for label, folder in (("home", contained.home), ("scratch", contained.scratch)):
        scan(folder, label, scrub)  # what the host kept for itself, such as a session file, is scanned too
    texts = {name: scrub.text(text, f"the host's {name}", neutral=True)
             for name, text in (("stdout", result.stdout), ("stderr", result.stderr))}
    messages = [item["text"] for item in result.log if item["kind"] == "message"]
    ran = scrub.value({"failure": result.failure, "exposure": result.exposure,  # what the run reported
                       "final_message": messages[-1] if messages else None, "requests": result.requests}, where)
    ran["log"] = [{name: value if name in host.FIXED and host.FIXED[name](value)  # a value the harness chose
                   else scrub.value(value, f"{where}/log/{number}/{name}") for name, value in item.items()}
                  for number, item in enumerate(result.log)]
    return ran, texts


def scan(folder, label, scrub):
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
