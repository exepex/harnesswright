"""The one way the harness describes a folder: a manifest of every entry in it (doc 11, Worlds).

A manifest maps each relative posix path to one entry string:

- `dir` for a folder, so an empty folder is part of the state;
- `file <sha256>` for a file, or `file <sha256> x` when any executable bit is set;
- `link <target>` for a symlink, which is never followed;
- `other` for a pipe, socket or device, only where the caller allows it (`other=True`), as the world after a run
  may hold one the agent made.

World hashes, the arm proof and world diffs all use this one representation, so a change of contents, of the
executable bit, of a folder or of a link is always a change. Any other kind of entry (a pipe, socket or
device) unless the caller allows it, and any entry that cannot be read, is refused, so a manifest is never
partial. The module uses only the standard library and imports nothing from the harness, so it can run in a jail.
"""

import hashlib
import json
import os
import stat

EXEC = "x"


class Unreadable(ValueError):
    """A folder that cannot be described in full: an entry that is not a folder, regular file or link, or one
    that cannot be read. A manifest is never partial."""


def entry(path, other=False):
    """The manifest entry of one path. Only a link, a folder or a regular file has one, or with `other` any entry,
    and any error while reading it raises Unreadable."""
    try:
        return _entry(path, other)
    except OSError as error:
        raise Unreadable(f"{path}: cannot be read: {error.strerror}") from None


def _entry(path, other=False):
    mode = os.lstat(path).st_mode
    if stat.S_ISLNK(mode):
        return "link " + os.readlink(path)
    if stat.S_ISDIR(mode):
        return "dir"
    if not stat.S_ISREG(mode) and other:
        return "other"
    if not stat.S_ISREG(mode):
        raise Unreadable(f"{path}: not a folder, regular file or link")
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return f"file {digest.hexdigest()}" + (f" {EXEC}" if mode & 0o111 else "")


def manifest(folder, skip=(), other=False):
    """{relative posix path: entry} for every entry under `folder`. Paths whose first part is in `skip` (such as
    `.git`) are left out. `other` allows pipes, sockets and devices (`entry`). Symlinked folders are recorded as
    links and not entered. Raise Unreadable when any entry cannot be read, so a manifest is never partial."""
    folder = os.fspath(folder)
    found = {}

    def refuse(error):
        raise Unreadable(f"{error.filename}: cannot be read: {error.strerror}")

    for root, dirs, names in os.walk(folder, onerror=refuse):
        if root == folder:
            dirs[:] = [d for d in dirs if d not in skip]
        for name in dirs + names:
            path = os.path.join(root, name)
            found[os.path.relpath(path, folder).replace(os.sep, "/")] = entry(path, other)
    return found


def digest(entries):
    """One hash for a manifest."""
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


def kind(value):
    """`dir`, `file` or `link`."""
    return value.split(" ", 1)[0]


def is_file(value):
    return kind(value) == "file"
