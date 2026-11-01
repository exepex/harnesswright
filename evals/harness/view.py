"""The grader view: what a grader sees of one bundle (doc 11, Evidence). Graders never read the full record.

The view is built from the bundle by allow lists and four rules, never by copying the bundle and deleting what is
known to be risky. Each rule is applied the same way in both arms, so the same run in either arm gives the same view.

- **Fields and paths.** The view holds only the fields in FIELDS, and only the world paths outside the overlay (both
  copies of the skill, and the folders above them while they only hold them) and outside the host's own files.
- **Actions.** A log entry is dropped when its action is on the overlay: it loads the skill, or its path or command
  names the skill or one of its paths (`on_overlay`). No without-skill run can act on the skill.
- **What the agent did, not what the world showed it.** A command is shown by what the agent ran
  (`COMMAND_FIELDS`), never by its output or exit code: the arms are different worlds, so what a world prints back
  (a listing, a line count, a commit's size) tells the arm, however it is filtered. Doc 11 gives graders the command
  list; the full record keeps the output for checks, audits and judges.
- **Text.** In every text the view shows (each log value, the final message, each file and each link target), a
  line that names the skill or one of its paths is removed, so the generated index row and every copy or edit of
  it goes too, and the run's folders become neutral words (`text`).

The diff is the diff of the view's own entries, so a change that only touched overlay lines is no change. A file's
entry is the hash of its view bytes, which the view holds as a blob. Before the run the bundle keeps no blob, so a
file's entry is the arm's own, and the index file's is the one it has in the without-skill arm, as the arms differ
there only by the row. A write's hash is shown only when it is the hash of its file's view bytes. What the agent
wrote of what it saw, such as a folder listing it saved to a file, or a word it made from the skill's name, is its
own output and is not hidden.

Standard library only.
"""

import hashlib
import os
import re

import evidence
import host
import manifest
import scrub
import world

FIELDS = ("case", "mode", "files_after", "diff", "log", "final_message")  # all a grader may see of a record
ACTION_FIELDS = ("path", "command")  # the fields that say what an action acts on
COMMAND_FIELDS = ("kind", "source", "command")  # all a grader sees of a command: what the agent ran


def view(record, blob):
    """The grader view of a bundle as `evidence.load` gives it: its view record and its blobs by hash."""
    overlay, folders = record["overlay"], record["folders"]
    words = world.names([overlay["skill"], *overlay["paths"]])
    places, own = overlay["paths"], record["own_files"]
    blobs, hashes = {}, {}  # hashes: {path: (bundle hash, view hash)}

    def after(path, entry):
        if manifest.is_file(entry):
            digest, rest = entry.split(" ")[1], entry[len("file ") + 64:]
            data = text(blob(digest), words, folders)
            hashes[path] = (digest, hashlib.sha256(data).hexdigest())
            blobs[hashes[path][1]] = data
            return f"file {hashes[path][1]}{rest}"
        if manifest.kind(entry) == "link":
            return "link " + text(entry[len("link "):], words, folders)
        return entry

    def before(path, entry):
        if evidence.covers(places, path, entry, entry):
            return None  # a folder that held the skill before the run is the overlay's
        if path == overlay["index"] and manifest.is_file(entry):
            return overlay["index_without"]
        return "link " + text(entry[len("link "):], words, folders) if manifest.kind(entry) == "link" else entry

    shown = {path: after(path, entry) for path, entry in record["files_after"].items()}
    old = {path: before(path, change["before"]) for path, change in record["diff"].items() if change["before"]}
    old = {path: entry for path, entry in old.items() if entry is not None}
    new = {path: shown[path] for path, change in record["diff"].items() if change["after"]}
    files = {path: entry for path, entry in shown.items()
             if path not in own and not evidence.covers(places, path, entry, entry)}
    changes = evidence.diff(old, new, places, own)
    named = [*files.values(), *(change["after"] for change in changes.values() if change["after"])]
    blobs = {digest: blobs[digest] for digest in {entry.split(" ")[1] for entry in named if manifest.is_file(entry)}}
    log = []
    root = next((path for path, word in folders.items() if word == scrub.NEUTRAL_FOLDERS["world"]), None)
    follows, read = False, set()  # whether the entry follows a dropped command; the paths the view shows read
    for item in record["log"]:
        if follows and host.part_of_command(item):
            continue  # it stands right after the command it came from, and goes with it
        follows = False
        if on_overlay(item, words):
            follows = item["kind"] == "command"
            continue
        written = item.get("path")
        item = {name: value if name in host.FIXED or not isinstance(value, str) else text(value, words, folders)
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
             "final_message": None if final is None else text(final, words, folders)}
    return {name: built[name] if name in built else record[name] for name in FIELDS}, blobs


def on_overlay(item, words):
    """Whether a log entry's action is on the overlay: a skill load, or a path or command that names it
    (`world.names`)."""
    return item["kind"] == "skill" or any(words.search(item.get(name, "")) for name in ACTION_FIELDS)


def text(value, words, folders):
    """`value` (text or bytes) without each line that names the skill or its paths (`words`, from `world.names`), and
    with each of the run's `folders` (`scrub.folders`) as its neutral word."""
    raw = isinstance(value, bytes)
    encode = (lambda word: word.encode()) if raw else (lambda word: word)
    find = re.compile(words.pattern.encode()) if raw else words
    kept = [line for line in value.splitlines(keepends=True) if not find.search(line)]
    value = (b"" if raw else "").join(kept)
    for folder in sorted(folders, key=len, reverse=True):
        value = value.replace(encode(folder), encode(folders[folder]))
    return value


def _relative(path, world):
    """A reported path as the manifest names it: relative to the world, as a host may report it absolute."""
    if world and path.startswith(world.rstrip("/") + "/"):
        return path[len(world.rstrip("/")) + 1:]
    return path
