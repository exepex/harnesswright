"""The grader view: what a grader sees of one bundle (doc 11, Evidence). Graders never read the full record.

One rule: a grader sees everything the run wrote and said, and the view removes only what the harness put there.
`ADDED` is the one list of what the harness puts there, and each item is removed at one place below, from what the
bundle records the harness added, never by a pattern over what the run wrote:

- `skill`: the installed skill, both copies and the folders above them while they only hold them, and every other
  file a team install adds (`evidence.places`), from the files after and from the diff (`evidence.covers`).
- `row`: the line the install adds to each file it edits in place (`edited`): each line of the index file that is
  the overlay's row byte for byte (`skills.with_rows`), and each line of a team profile that is the version line
  naming a release manifest the install added (`teamrelease.with_version`). A line the run changed, or wrote in
  another file, is the run's.
- `lead`: the lead line that pins the skill's load (`host.LEAD`), as each line of a text that holds it, and the load
  it pins: the host's skill event for the skill, and a read of the `SKILL.md` of an installed copy. A command the
  run typed stays whole, whatever it reads.
- `arm`: every field of the record outside FIELDS: the arm, the host, its model, timings, what the host exposed,
  its requests and its failure.
- `world`: what the world printed back, a command's output and exit code (`COMMAND_FIELDS`): the arms are
  different worlds. Script checks decide outcomes on the full bundle.
- `host`: the host's own files, which it writes on an empty run (`own_files`), and the run's real folders, which
  become their neutral words (`scrub.folders`).

Everything else is the run's, and the view shows it whole: every file it wrote, under any name, every line of it;
every action and every command as it ran it; its final message. So a page names the skill wherever the run did. In
a case with a without-skill arm that may tell the arm; the paired goldens (`goldens.unpaired`) test that it moves
no settled answer (doc 11, Graders).

The diff is the diff of the view's own entries, so a change that only touched the overlay is no change. A file's
entry is the hash of its view bytes, which the view holds as a blob. Before the run the bundle keeps no blob, so a
file the install edits in place (the index, a team profile) has the entry it has in the without-skill arm. A write's
hash is shown only when it is the hash of its file's view bytes.

Standard library only.
"""

import hashlib
import os

import evidence
import host
import manifest
import scrub
import teamrelease

ADDED = ("skill", "row", "lead", "arm", "world", "host")  # what the harness puts there: all the view removes
FIELDS = ("case", "mode", "files_after", "diff", "log", "final_message")  # all a grader may see of a record
COMMAND_FIELDS = ("kind", "source", "command")  # all a grader sees of a command: what the agent ran


def view(record, blob):
    """The grader view of a bundle as `evidence.load` gives it: its view record and its blobs by hash."""
    overlay, folders = record["overlay"], record["folders"]
    places, own, leads = evidence.places(overlay), record["own_files"], lead_lines(overlay)
    edited = overlay.get("edited") or {overlay["index"]: overlay.get("index_without")}  # stored before profiles
    blobs, hashes = {}, {}  # hashes: {path: (bundle hash, view hash)}

    def added(path, line):
        """Whether `line` of the file at `path` is the line the install adds to it: the index row, byte for byte,
        or a team profile's version line, which names a release manifest the install added."""
        if path == overlay["index"]:
            return bool(overlay.get("row")) and line.rstrip(b"\r\n") == overlay["row"].encode()
        named = teamrelease.stated(line.decode("utf-8", "replace"))
        return named is not None and evidence.covers(places, named)

    def after(path, entry):
        if manifest.is_file(entry):
            digest, rest = entry.split(" ")[1], entry[len("file ") + 64:]
            data = blob(digest)
            if path in edited:  # a file the install edits in place, without the line it adds
                data = b"".join(line for line in data.splitlines(keepends=True) if not added(path, line))
            data = text(data, leads, folders)
            hashes[path] = (digest, hashlib.sha256(data).hexdigest())
            blobs[hashes[path][1]] = data
            return f"file {hashes[path][1]}{rest}"
        if manifest.kind(entry) == "link":
            return "link " + text(entry[len("link "):], leads, folders)
        return entry

    def before(path, entry):
        if evidence.covers(places, path, entry, entry):
            return None  # a folder that held the skill before the run is the overlay's
        if path in edited and manifest.is_file(entry):
            return edited[path]
        return "link " + text(entry[len("link "):], leads, folders) if manifest.kind(entry) == "link" else entry

    entries = {path: after(path, entry) for path, entry in record["files_after"].items()}
    old = {path: before(path, change["before"]) for path, change in record["diff"].items() if change["before"]}
    old = {path: entry for path, entry in old.items() if entry is not None}
    new = {path: entries[path] for path, change in record["diff"].items() if change["after"]}
    files = {path: entry for path, entry in entries.items()
             if path not in own and not evidence.covers(places, path, entry, entry)}
    changes = evidence.diff(old, new, places, own)
    named = [*files.values(), *(change["after"] for change in changes.values() if change["after"])]
    blobs = {digest: blobs[digest] for digest in {entry.split(" ")[1] for entry in named if manifest.is_file(entry)}}
    log = []
    root = next((path for path, word in folders.items() if word == scrub.NEUTRAL_FOLDERS["world"]), None)
    loads = {os.path.normpath(f"{path}/SKILL.md") for path in overlay["paths"]}  # the files the pin loads
    read = set()  # the paths the view shows read
    for item in record["log"]:
        if item["kind"] == "skill" and item["name"] == overlay["skill"] or item["kind"] == "read" and \
                os.path.normpath(_relative(item["path"], root)) in loads:
            continue  # the load the lead line pins
        written = item.get("path")
        item = {name: value if name in host.FIXED or not isinstance(value, str) else text(value, leads, folders)
                for name, value in item.items()}
        if item["kind"] == "read":  # a file's inferred read is shown once, the first time, the same in either arm
            if item["source"] == "inferred" and os.path.normpath(item["path"]) in read:
                continue
            read.add(os.path.normpath(item["path"]))
        if item["kind"] == "command":  # what the world printed back differs between the arms, so it stays out
            item = {name: item[name] for name in COMMAND_FIELDS}
        if item["kind"] == "write" and item["sha256"] is not None:
            seen = hashes.get(_relative(written, root))
            item["sha256"] = seen[1] if seen and seen[0] == item["sha256"] else None
        log.append(item)
    final = record["final_message"]
    built = {"files_after": files, "diff": changes, "log": log,
             "final_message": None if final is None else text(final, leads, folders)}
    return {name: built[name] if name in built else record[name] for name in FIELDS}, blobs


def lead_lines(overlay):
    """The lead line that pins the load of the overlay's skill at each of its installed copies (`host.LEAD`)."""
    return [host.LEAD.format(skill=overlay["skill"], path=f"{path}/SKILL.md") for path in overlay["paths"]]


def text(value, leads, folders):
    """`value` (text or bytes) without each line that holds one of `leads` (`lead_lines`), and with each of the run's
    `folders` (`scrub.folders`) as its neutral word."""
    raw = isinstance(value, bytes)
    encode = (lambda word: word.encode()) if raw else (lambda word: word)
    kept = [line for line in value.splitlines(keepends=True) if not any(encode(lead) in line for lead in leads)]
    value = (b"" if raw else "").join(kept)
    for folder in sorted(folders, key=len, reverse=True):
        value = value.replace(encode(folder), encode(folders[folder]))
    return value


def _relative(path, world):
    """A reported path as the manifest names it: relative to the world, as a host may report it absolute."""
    if world and path.startswith(world.rstrip("/") + "/"):
        return path[len(world.rstrip("/")) + 1:]
    return path
