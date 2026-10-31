"""The one way the harness describes a folder: a manifest of every entry in it (doc 11, Worlds).

A manifest maps each relative posix path to one entry string:

- `dir` for a folder, so an empty folder is part of the state;
- `file <sha256>` for a file, or `file <sha256> x` when any executable bit is set;
- `link <target>` for a symlink, which is never followed.

World hashes, the arm proof and world diffs all use this one representation, so a change of contents, of the
executable bit, of a folder or of a link is always a change. The module uses only the standard library and
imports nothing from the harness, so the same code can run inside a jail.
"""

import hashlib
import json
import os

EXEC = "x"


def entry(path):
    """The manifest entry of one path."""
    if os.path.islink(path):
        return "link " + os.readlink(path)
    if os.path.isdir(path):
        return "dir"
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    executable = os.stat(path).st_mode & 0o111
    return f"file {digest.hexdigest()}" + (f" {EXEC}" if executable else "")


def manifest(folder, skip=()):
    """{relative posix path: entry} for every entry under `folder`. Paths whose first part is in `skip` (such as
    `.git`) are left out. Symlinked folders are recorded as links and not entered."""
    folder = os.fspath(folder)
    found = {}
    for root, dirs, names in os.walk(folder):
        if root == folder:
            dirs[:] = [d for d in dirs if d not in skip]
        for name in dirs + names:
            path = os.path.join(root, name)
            found[os.path.relpath(path, folder).replace(os.sep, "/")] = entry(path)
    return found


def digest(entries):
    """One hash for a manifest."""
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


def kind(value):
    """`dir`, `file` or `link`."""
    return value.split(" ", 1)[0]


def is_file(value):
    return kind(value) == "file"
