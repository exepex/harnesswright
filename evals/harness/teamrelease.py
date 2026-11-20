"""What a team skill's arms take from the release, and the proof that they took it byte for byte (doc 12, Team
worlds).

A team installs harnesswright as its release zip, unpacked into the folder its profile names (`.harness/profile.yaml`,
`harnesswright.folder`, doc 07). So, file by file:

- **with skill**: the case world, the skill's release folder, and, where the profile names a folder, the release's
  run-time files in it: the paths the release manifest's `run-time` list covers (build.py declares them once);
- **previous version**: the same set, from the previous commit's release;
- **without skill**: the case world only. In a task case, where lift is measured, nothing comes from the release, so a
  team skill's task case installs no sibling. A trigger case measures the description, so it still installs every
  other skill as a sibling in both arms, as in real use (`world.plan`).

One reader, `check`, proves every installed file against the hashes of the release manifest beside the skill's
folder: the skill folder against its `files`, the run-time files against `run-time-files`. manifest.json cannot
hold its own hash, so it is copied from that same release, which the other hashes vouch for. A file with no hash, a
hash with no file, or other bytes is a harness fault: the release is not what it says, so the round stops.

Standard library only.
"""

import json
import re
from pathlib import Path

from cases import CaseError, is_path

PROFILE = ".harness/profile.yaml"
SELF = "manifest.json"  # on the run-time list, but it cannot hold its own hash
# The one shape this reader accepts for the profile's release folder: a top-level `harnesswright:` block whose
# `folder:` line holds a relative path, quoted or not, with an optional trailing `/` and comment.
BLOCK = re.compile(r"^harnesswright:[ \t]*(?:#.*)?\n((?:[ \t]+.*\n|[ \t]*\n)*)", re.MULTILINE)
FOLDER = re.compile(r"^[ \t]+folder:[ \t]*([\"']?)([^\"'#\s]+?)/?\1[ \t]*(?:#.*)?$", re.MULTILINE)


def release_folder(world):
    """The folder the world's profile unpacks the release into, relative to the world, or None without one."""
    path = Path(world) / PROFILE
    if not path.is_file():
        return None
    block = BLOCK.search(path.read_text(encoding="utf-8", errors="replace") + "\n")
    found = FOLDER.search(block.group(1)) if block else None
    if not found:
        return None
    if not is_path(found.group(2)):
        raise CaseError(f"{PROFILE}: harnesswright.folder {found.group(2)!r} is not a path inside the world")
    return found.group(2)


def release(skill_dir, name):
    """(release folder, its manifest) beside the skill folder `skill_dir`. A harness fault when it has none, or
    when the manifest does not hash the skill and the run-time files."""
    root = Path(skill_dir).parent
    try:
        data = json.loads((root / SELF).read_text(encoding="utf-8"))
        entry = data["skills"][name]
        if not (isinstance(entry["files"], dict) and isinstance(data["run-time"], list)
                and isinstance(data["run-time-files"], dict)):
            raise TypeError("no hashes")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise CaseError(f"harness fault: {skill_dir} is not a release skill whose manifest hashes its files: "
                        f"{type(error).__name__}: {error}") from None
    return root, data


def run_time(data):
    """The release paths the manifest's run-time list covers: every hashed file, and the manifest itself."""
    return sorted([*data["run-time-files"], SELF] if SELF in data["run-time"] else data["run-time-files"])


def check(where, files, hashes):
    """Raise a harness fault unless `files` ({path: manifest entry}) hold exactly the files `hashes` names, each
    with its bytes. Folders are not files."""
    found = {rel: e.split(" ")[1] for rel, e in files.items() if e.startswith("file ")}
    missing, extra = sorted(set(hashes) - set(found)), sorted(set(found) - set(hashes))
    differ = sorted(rel for rel in set(found) & set(hashes) if found[rel] != hashes[rel])
    if missing or extra or differ:
        raise CaseError(f"harness fault: {where}: not what the release manifest hashes: missing {missing}, "
                        f"unhashed {extra}, different {differ}")
