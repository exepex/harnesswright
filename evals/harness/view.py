"""The grader view: what a grader sees of one bundle (doc 11, Evidence). Graders never read the full record.

One rule: the view is built from the bundle by allow lists, never by copying it and deleting what is known to be
risky. It holds only the fields in FIELDS, and only the world paths outside the overlay (`evidence.covers`) and
outside the host's own files. Everything the with-skill overlay added to the arm is left out, so the same run in
either arm gives the same view:

- both copies of the skill, and the folders above them while they only hold them;
- the generated index row, as a line of the index file and of any text in the view (`unrow`);
- every action in the log that loads the skill or names it or its paths (`marked`);
- the skill's name and paths in the agent's messages and final message, which become neutral words.

A file's entry before the run is shown by its kind and mode only, as a bundle keeps no blob of it and the index file
differs between the arms before the run. Every file in the view's files after names a blob of the view, and a write's
hash follows its file when the view changed that file's bytes.

Standard library only.
"""

import hashlib

import evidence
import manifest
import scrub

FIELDS = ("case", "mode", "files_after", "diff", "log", "final_message")  # all a grader may see of a record


def view(record, blob):
    """The grader view of a bundle as `evidence.load` gives it: its view record and its blobs by hash."""
    overlay = record["overlay"]
    places, own = overlay["paths"], set(record["own_files"])
    blobs, renamed = {}, {}

    def shown(path, entry):
        if not manifest.is_file(entry):
            return entry
        digest, rest = entry.split(" ")[1], entry[len("file ") + 64:]
        data = blob(digest)
        if path == overlay["index"]:
            data = unrow(data, overlay["row"])
        renamed[digest] = hashlib.sha256(data).hexdigest()
        blobs[renamed[digest]] = data
        return f"file {renamed[digest]}{rest}"

    def outside(path, entry=None):
        return path not in own and not evidence.covers(places, path, entry, entry)

    files = {path: shown(path, entry) for path, entry in record["files_after"].items() if outside(path, entry)}
    changes = {path: {"before": _kind(change["before"]), "after": files.get(path) if change["after"] else None}
               for path, change in record["diff"].items() if outside(path)}
    log = []
    for item in record["log"]:
        item = {name: unrow(value, overlay["row"]) if isinstance(value, str) and name not in ("kind", "source")
                else value for name, value in item.items()}
        if item["kind"] == "message":
            item["text"] = _neutral(item["text"], overlay)  # the agent's words are kept, as the final message is
        elif marked(item, overlay):
            continue
        if item["kind"] == "write" and item["sha256"] is not None:
            item["sha256"] = renamed.get(item["sha256"], item["sha256"])
        log.append(item)
    final = record["final_message"]
    if final is not None:
        final = _neutral(unrow(final, overlay["row"]), overlay)
    built = {"files_after": files, "diff": changes, "log": log, "final_message": final}
    return {name: built[name] if name in built else record[name] for name in FIELDS}, blobs


def unrow(value, row):
    """`value` (text or bytes) without the index row's line, wherever it stands; unchanged when there is no row."""
    if not row:
        return value
    line, empty = (row, "") if isinstance(value, str) else (row.encode(), b"")
    for ending in ("\r\n", "\n"):
        value = value.replace(line + (ending if isinstance(value, str) else ending.encode()), empty)
    return value.replace(line, empty)


def marked(item, overlay):
    """Whether an action in the log is the overlay's: it loads the skill, or any of its text names the skill or its
    paths. The view drops it, as acting on the skill tells the arm. A message is the agent's words and is kept."""
    if item["kind"] == "skill":
        return True
    words = [overlay["skill"], *overlay["paths"]]
    return any(isinstance(value, str) and any(word in value for word in words)
               for name, value in item.items() if name not in ("kind", "source"))


def _neutral(text, overlay):
    words = {overlay["skill"]: scrub.NEUTRAL_NAME, **{path: scrub.NEUTRAL_PATH for path in overlay["paths"]}}
    for word in sorted(words, key=len, reverse=True):
        text = text.replace(word, words[word])
    return text


def _kind(entry):
    """An entry before the run as the view shows it: a file by its kind and mode, any other entry as it is."""
    if entry is None or not manifest.is_file(entry):
        return entry
    return "file" + entry[len("file ") + 64:]
