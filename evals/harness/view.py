"""The grader view: what a grader sees of one bundle (doc 11, Evidence). Graders never read the full record.

The view is built from the bundle by allow lists and four rules, never by copying the bundle and deleting what is
known to be risky. Each rule is applied the same way in both arms, so the same run in either arm gives the same view.

- **The skill's name, in any spelling.** The view never shows the skill's name or one of its paths, whole or inside a
  longer name such as `rules-text-<skill>.core.md`: one pattern finds them (`spelled`), and every rule below that
  names the skill uses it, the checks' question of what the view shows too (`overlay_names`, `checks.decide`).
- **A run's rules files.** The view never shows the files a run writes beside its rules, `rules.md` and each
  `rules-text-<skill>.<stack>.md` of a run folder, in either arm: only a skill's resolver writes them, so they tell
  the arm whichever skill they name. Their names are the resolver's own (`RUN_FILES`, from `v2/build/runfiles.py`),
  never a list here. A path that is one is left out, and an action on one is the overlay's (`overlay_names`).
- **Fields and paths.** The view holds only the fields in FIELDS, and only the world paths outside the overlay (both
  copies of the skill, and the folders above them while they only hold them), outside the host's own files, that do
  not name the skill (`spelled`) and that are not a run's rules file.
- **Actions.** A log entry is dropped when its action is on the overlay: it loads the skill, or its path, command or
  refused action names the skill, one of its paths, or a folder above them that only the overlay made
  (`on_overlay`, `overlay_names`). The view hides what is on the overlay, not what sits beside it: a command is
  shown without its pipelines on the overlay and what depends on them, cut where `shell.programs` splits it, and
  is dropped whole only when nothing else is left or no clean cut can be made (`shown`, `shell.cut`). A read
  inferred from a cut command goes when only the part cut away names it.
- **What the agent did, not what the world showed it.** A command is shown by what the agent ran
  (`COMMAND_FIELDS`), never by its output or exit code: the arms are different worlds, so what a world prints back
  (a listing, a line count, a commit's size) tells the arm, however it is filtered. Doc 11 gives graders the command
  list; the full record keeps the output for checks, audits and judges.
- **Text.** In every text the view shows (each log value, the final message, each file and each link target), a
  line that names the skill or one of its paths is removed, so the generated index row and every copy or edit of
  it goes too, and the run's folders become neutral words (`text`).

The diff is the diff of the view's own entries, so a change that only touched overlay lines is no change. A file's
entry is the hash of its view bytes, which the view holds as a blob. Before the run the bundle keeps no blob, so a
file's entry is the arm's own, and a file the install edits in place (the index, a team profile) has the entry it
has in the without-skill arm, as the arms differ there only by the line the install adds. A write's hash is shown
only when it is the hash of its file's view bytes. What the agent wrote of what it saw, such as a folder listing it
saved to a file, or a word it made from the skill's name, is its own output and is not hidden.

Standard library only.
"""

import ast
import hashlib
import os
import re
from pathlib import Path, PurePosixPath

import evidence
import host
import manifest
import scrub
import shell

FIELDS = ("case", "mode", "files_after", "diff", "log", "final_message")  # all a grader may see of a record
ACTION_FIELDS = ("path", "command", "action")  # the fields that say what an action acts on
COMMAND_FIELDS = ("kind", "source", "command")  # all a grader sees of a command: what the agent ran
RUNFILES = Path(__file__).resolve().parents[2] / "v2" / "build" / "runfiles.py"  # the resolver's names of its files


def view(record, blob):
    """The grader view of a bundle as `evidence.load` gives it: its view record and its blobs by hash."""
    overlay, folders = record["overlay"], record["folders"]
    words = spelled([overlay["skill"], *evidence.places(overlay)])
    acts = overlay_names(overlay, record["files_after"], record["diff"])  # what puts an action on the overlay
    places, own = evidence.places(overlay), record["own_files"]
    edited = overlay.get("edited") or {overlay["index"]: overlay.get("index_without")}  # stored before profiles
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
        if path in edited and manifest.is_file(entry):
            return edited[path]
        return "link " + text(entry[len("link "):], words, folders) if manifest.kind(entry) == "link" else entry

    entries = {path: after(path, entry) for path, entry in record["files_after"].items()}
    old = {path: before(path, change["before"]) for path, change in record["diff"].items() if change["before"]}
    old = {path: entry for path, entry in old.items() if entry is not None}
    new = {path: entries[path] for path, change in record["diff"].items() if change["after"]}
    hidden = lambda path: words.search(path) or RUN_FILES.search(path)  # noqa: E731
    files = {path: entry for path, entry in entries.items()
             if path not in own and not evidence.covers(places, path, entry, entry) and not hidden(path)}
    changes = {path: change for path, change in evidence.diff(old, new, places, own).items() if not hidden(path)}
    named = [*files.values(), *(change["after"] for change in changes.values() if change["after"])]
    blobs = {digest: blobs[digest] for digest in {entry.split(" ")[1] for entry in named if manifest.is_file(entry)}}
    log = []
    root = next((path for path, word in folders.items() if word == scrub.NEUTRAL_FOLDERS["world"]), None)
    names = None  # right after a command the view drops, False; after one it cuts, what its shown part names
    read = set()  # the paths the view shows read
    for item in record["log"]:
        if names is not None and host.part_of_command(item):
            if names is False or item["kind"] != "read" or not names(item["path"]):
                continue  # it stands right after the command it came from, and goes with the part not shown
        else:
            names = None
        action = shown(item, acts)
        if action is None:
            names = False if item["kind"] == "command" else None
            continue
        if action is not item:  # a command cut to its pipelines that do not name the skill
            names = _named_by(action["command"], item["command"], os.path.normpath(root) if root else ".")
        item, written = action, item.get("path")
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


def overlay_names(overlay, files_after, diff):
    """The pattern that finds what puts an action on the overlay: the skill's name and paths (`spelled`), a run's
    rules files (`RUN_FILES`), and,
    as a path, each folder above one of its paths that the overlay alone made: before the run it held nothing but
    the overlay (`evidence.covers`), or was not there. A folder of that name the world holds itself does not count,
    and both arms find the same folders, so the same run in either arm gives the same view."""
    places = evidence.places(overlay)
    before = {path: entry for path, entry in files_after.items() if path not in diff}
    before.update({path: change["before"] for path, change in diff.items() if change["before"]})
    above = {str(folder) for place in places for folder in PurePosixPath(place).parents if str(folder) != "."}
    only = sorted(folder for folder in above
                  if all(evidence.covers(places, path) for path in before if path.startswith(folder + "/")))
    pattern = spelled([overlay["skill"], *places]).pattern
    # a folder is named as a path from the world: at a word's start or after ./, whole or with a path below it
    start, end = r"""(?<![^\s'"`;&|<>()=])(?:\./)?""", r"""(?=/|$|[\s'"`;&|<>()*])"""
    folders = "".join(f"|{start}{re.escape(folder)}{end}" for folder in only)
    return re.compile(pattern + folders + "|" + RUN_FILES.pattern, re.ASCII)


def shown(item, words):
    """A log entry as the view shows its action, or None when it shows none. An action on the overlay
    (`on_overlay`) is dropped, except a command whose every pipeline that names the skill can be cut away
    (`shell.cut`): it is shown as its other pipelines. Checks ask this of the view (`checks.decide`)."""
    if not on_overlay(item, words):
        return item
    if item["kind"] != "command":
        return None
    command = shell.cut(item["command"], lambda part: bool(words.search(part)))
    if not command or not command.strip(" \t"):
        return None
    return {**item, "command": command, "exit_code": None}  # the code was the whole command's, not its shown part's


def run_names(source=RUNFILES):
    """[the resolver's own names of a run's rules files]: `RULES_MD` and `RULES_TEXT`, built on `RUN`, in `source`,
    with their fields such as `{run}` and `{skill}`. Raise ValueError when the source does not name them as strings."""
    known = {}
    for node in ast.parse(source.read_text()).body:
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] in (["RUN"], ["RULES_MD"],
                                                                                              ["RULES_TEXT"]):
            known[node.targets[0].id] = _joined(node.value, known)
    if set(known) != {"RUN", "RULES_MD", "RULES_TEXT"}:
        raise ValueError(f"{source}: names no RUN, RULES_MD and RULES_TEXT")
    return [known["RULES_MD"], known["RULES_TEXT"]]


def run_files(source=RUNFILES):
    """The pattern that finds a run's rules files (`run_names`) as a path from the world, whole, each of their
    fields any one path part."""
    part = r"""[^/\s'"`;&|<>()*]+"""
    names = [re.sub(r"\\\{\w+\\\}", lambda _: part, re.escape(name)) for name in run_names(source)]
    return re.compile(r"""(?<![^/\s'"`;&|<>()=])(?:\./)?(?:""" + "|".join(names) + r""")(?=$|[\s'"`;&|<>()*])""",
                      re.ASCII)


def _joined(node, known):
    """The string a module-level expression of strings and names joined by `+` gives."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in known:
        return known[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _joined(node.left, known) + _joined(node.right, known)
    raise ValueError(f"not a string of strings and names: {ast.dump(node)}")


def spelled(words):
    """The one pattern that finds each of `words` (the skill's name and paths) as the view hides it: in any spelling,
    whole or inside a longer name, so `rules-text-<skill>.core.md` or `<skill>_notes` names the skill. A name is
    found where no ASCII letter or digit stands next to it, so a skill named `test` is still not found in `pytest`;
    a `-`, `_` or `.` beside it is a separator, not part of it. Longer words are tried first."""
    found = sorted(set(words), key=lambda word: (-len(word), word))
    return re.compile("(?<![A-Za-z0-9])(?:" + "|".join(re.escape(word) for word in found) + ")(?![A-Za-z0-9])",
                      re.ASCII)


def on_overlay(item, words):
    """Whether a log entry's action is on the overlay: a skill load, or a path, command or refused
    action that names it (`spelled`)."""
    return item["kind"] == "skill" or any(words.search(item.get(name, "")) for name in ACTION_FIELDS)


def text(value, words, folders):
    """`value` (text or bytes) without each line that names the skill or its paths (`words`, from `spelled`), and
    with each of the run's `folders` (`scrub.folders`) as its neutral word."""
    raw = isinstance(value, bytes)
    encode = (lambda word: word.encode()) if raw else (lambda word: word)
    find = re.compile(words.pattern.encode()) if raw else words
    kept = [line for line in value.splitlines(keepends=True) if not find.search(line)]
    value = (b"" if raw else "").join(kept)
    for folder in sorted(folders, key=len, reverse=True):
        value = value.replace(encode(folder), encode(folders[folder]))
    return value


def _named_by(shown, command, root):
    """Whether a read inferred from `command` stays with its `shown` part: unless only the part cut away names it
    (`host.naming`), as a read its adapter inferred by its own reading belongs to no one part."""
    kept, whole = host.naming(shown, root), host.naming(command, root)
    return lambda path: kept(path) or not whole(path)


def _relative(path, world):
    """A reported path as the manifest names it: relative to the world, as a host may report it absolute."""
    if world and path.startswith(world.rstrip("/") + "/"):
        return path[len(world.rstrip("/")) + 1:]
    return path


RUN_FILES = run_files()  # a run's rules files, as the resolver names them
