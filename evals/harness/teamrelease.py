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

One reader, `prove`, proves a release skill and its run-time files, and its proof is chosen by the manifest's
`rulebook-version`, never by which keys it has:

- **hashes**, from 0.8.0 (`HASHED_FROM`), the first release whose manifest hashes what it ships: the skill folder
  against its `files`, and every run-time file against `run-time-files`. manifest.json cannot hold its own hash, so
  it is copied from that same release, which the other hashes vouch for. A missing `run-time` list or hash, a file
  with no hash, a hash with no file, or other bytes is a harness fault: the release is not what it says.
- **commit**, before 0.8.0, and only for a previous version: the folder is read from its commit by
  `rounds.previous`, which holds it to the sha256 the round recorded, and the run-time files are the files of that
  commit's release that the current release's `run-time` list covers.

Where the profile names a folder, the arm's profile also gets the `version:` line a team that installed that
release has: its manifest's `rulebook-version`, which `v2/build/resolve.py` holds the profile to (`with_version`).
So a case's profile states the folder and what else it tests, never a version that must track `v2/VERSION`. One
rule keeps that line from changing anything a case cites: it moves no line of the case's profile. So the
`harnesswright` block holds only blank lines, comments and its one `folder:` line (an allow list: any other key is
refused), the block is the profile's last entry, and the version line goes at its end. A case that tests a
mismatch on purpose declares the version it wants (`profile_version`, cases.py). The line says it is checked
against the release manifest, a file of the install, so the grader view removes it as it removes the index row,
and every arm shows the same profile.

A release that is neither is a harness fault, and the round stops. `rounds.plan` proves each arm before any case
runs and records which proof each had. A profile with a `harnesswright` entry in any other shape is refused, never
read as naming no folder.

Standard library only.
"""

import hashlib
import json
import re
from pathlib import Path

from cases import CaseError, is_path

PROFILE = ".harness/profile.yaml"
SELF = "manifest.json"  # on the run-time list, but it cannot hold its own hash
HASHED_FROM = (0, 8, 0)
# The one shape this reader accepts for the profile's release folder: a top-level `harnesswright:` block whose
# `folder:` line holds a relative path, quoted or not, with an optional trailing `/` and comment.
ENTRY = re.compile(r"^harnesswright[ \t]*:", re.MULTILINE)
BLOCK = re.compile(r"^harnesswright:[ \t]*(?:#.*)?\n((?:[ \t]+.*\n|[ \t]*\n)*)", re.MULTILINE)
FOLDER = re.compile(r"^[ \t]+folder:[ \t]*([\"']?)([^\"'#\s]+?)/?\1[ \t]*(?:#.*)?$", re.MULTILINE)
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
ALLOWED = re.compile(r"[ \t]*(?:#.*)?")  # beside the one `folder:` line, a block line may be blank or a comment


def release_folder(world):
    """The folder the world's profile unpacks the release into, relative to the world, or None when the profile,
    or its `harnesswright` entry, is not there. An entry in another shape, a block that holds more than its folder
    and comments, or one that is not the profile's last entry, is refused."""
    path = Path(world) / PROFILE
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace") + "\n"
    if not ENTRY.search(text):
        return None
    block = BLOCK.search(text)
    found = FOLDER.search(block.group(1)) if block else None
    if not found:
        raise CaseError(f"{PROFILE}: the harnesswright entry is not a block with a `folder:` line, the one shape "
                        "this reader takes")
    if not is_path(found.group(2)):
        raise CaseError(f"{PROFILE}: harnesswright.folder {found.group(2)!r} is not a path inside the world")
    lines = block.group(1).splitlines()
    other = [line for line in lines if not ALLOWED.fullmatch(line) and not FOLDER.fullmatch(line)]
    if other or sum(1 for line in lines if FOLDER.fullmatch(line)) != 1:
        raise CaseError(f"{PROFILE}: the harnesswright block holds only its one `folder:` line and comments, not "
                        f"{(other or ['a second folder'])[0].strip()!r}; the harness writes each arm's version from "
                        "its release, and a case that tests another declares profile_version")
    if text[block.end():].strip():
        raise CaseError(f"{PROFILE}: the harnesswright block is not the profile's last entry; the harness writes the "
                        "version line at its end, where it moves no line a case cites")
    return found.group(2)


def with_version(data, folder, version):
    """The profile bytes `data`, which `release_folder` read, with `version` as the last line of its
    `harnesswright` block, which is the profile's last entry, so no line of `data` moves. It is indented like the
    `folder:` line and says it is checked against the release manifest in `folder`."""
    text = data.decode("utf-8")
    indent = re.match(r"[ \t]*", FOLDER.search(BLOCK.search(text + "\n").group(1)).group(0)).group(0)
    lines = text.splitlines(keepends=True)
    last = max(n for n, line in enumerate(lines) if line.strip()) + 1  # after the block's last line that says anything
    lines[last - 1] = lines[last - 1].rstrip("\r\n") + "\n"
    lines.insert(last, f'{indent}version: "{version}"  # checked against {folder}/{SELF}\n')
    return "".join(lines).encode("utf-8")


def version_of(root):
    """The `rulebook-version` of the release in `root`, as its manifest states it."""
    return _manifest(root)[0]["rulebook-version"]


def covers(listed, rel):
    """True when a run-time list covers the release path `rel`, as v2/build/resolve.py `covers` reads it: it names
    it, or a folder (`.../`) above it."""
    return any(rel == p or (p.endswith("/") and rel.startswith(p)) for p in listed)


def _manifest(root):
    try:
        data = json.loads((Path(root) / SELF).read_text(encoding="utf-8"))
        version = VERSION.fullmatch(data["rulebook-version"])
        if not version:
            raise ValueError(f"rulebook-version {data['rulebook-version']!r} is not a version")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise CaseError(f"harness fault: {root}/{SELF} is not a release manifest with a rulebook-version: "
                        f"{type(error).__name__}: {error}") from None
    return data, tuple(int(n) for n in version.groups())


def _covered(root, listed):
    """The release files under `root` that the run-time list `listed` covers, the manifest itself included."""
    root = Path(root)
    return sorted(rel for rel in (p.relative_to(root).as_posix() for p in root.rglob("*")
                                  if p.is_file() and not p.is_symlink()) if covers(listed, rel))


def check(where, found, hashes):
    """Raise a harness fault unless `found` ({path: sha256}) holds exactly the files `hashes` names, with its
    bytes."""
    missing, extra = sorted(set(hashes) - set(found)), sorted(set(found) - set(hashes))
    differ = sorted(rel for rel in set(found) & set(hashes) if found[rel] != hashes[rel])
    if missing or extra or differ:
        raise CaseError(f"harness fault: {where}: not what the release manifest hashes: missing {missing}, "
                        f"unhashed {extra}, different {differ}")


def prove(skill_dir, name, files, current=None):
    """(release folder, proof, run-time paths) of the release skill `skill_dir`, whose tracked files hash to
    `files` ({path: sha256}). `current` is the release skill under test; it is given only when `skill_dir` is a
    previous version, the one arm a release from before 0.8.0 may come from."""
    root = Path(skill_dir).parent
    data, version = _manifest(root)
    if version < HASHED_FROM:
        if current is None or Path(current).resolve() == Path(skill_dir).resolve():
            raise CaseError(f"harness fault: {root} was built at {data['rulebook-version']}, before releases hashed "
                            "their files (0.8.0); only a previous version is proved by its commit")
        listed = _manifest(Path(current).parent)[0].get("run-time")
        if not isinstance(listed, list):
            raise CaseError(f"harness fault: the release under test, {Path(current).parent}, has no run-time list")
        return root, "commit", _covered(root, listed)
    entry = data.get("skills", {}).get(name) if isinstance(data.get("skills"), dict) else None
    for key, value in (("skills." + name + ".files", (entry or {}).get("files")),
                       ("run-time-files", data.get("run-time-files"))):
        if not isinstance(value, dict):
            raise CaseError(f"harness fault: {root}/{SELF} is {data['rulebook-version']} but has no {key} hashes")
    if not isinstance(data.get("run-time"), list):
        raise CaseError(f"harness fault: {root}/{SELF} is {data['rulebook-version']} but has no run-time list")
    check(f"{name}'s folder", files, entry["files"])
    paths = _covered(root, data["run-time"])
    check("the run-time files", {rel: hashlib.sha256((root / rel).read_bytes()).hexdigest()
                                 for rel in paths if rel != SELF}, data["run-time-files"])
    return root, "hashes", paths


def proof(skill_dir, name, current=None):
    """What a round records of the release skill `skill_dir`, from its tracked files: the proof `prove` gives it and
    every run-time file an arm installs with it, by its sha256 (`run_time`), but for the manifest: it hashes the
    skills themselves and states the version, so it changes with any skill, and it is proved by the other hashes."""
    import skills  # the one reader of a skill's tracked files
    files, _ = skills.skill_files(skill_dir, name)
    root, how, paths = prove(skill_dir, name, {rel: hashlib.sha256(data).hexdigest() for rel, data in files.items()},
                             current)
    return {"proof": how, "run_time": {rel: hashlib.sha256((root / rel).read_bytes()).hexdigest() for rel in paths
                                       if rel != SELF}}


def installed(record, name, arm):
    """What arm `arm` (`with_skill` or `previous_version`) of the round whose manifest is `record` installs for the
    skill `name`: its folder's hash and, for a team skill, its run-time files by hash (`release_proof`, `proof`), or
    None for a release proof recorded before run-time files were. The previous-version check compares it whole and
    the setup takes the with-skill arm's run-time files from it; results and versions read the folder hash alone,
    as earlier rounds recorded it. It holds no proof label, which names how a release was proved, not what it
    installs."""
    folder, kept = record["skills"] if arm == "with_skill" else record["previous"], record.get("release_proof", {})
    kept = kept.get(name, {}).get(arm)
    return {"sha256": folder.get(name, {}).get("sha256"), "run_time": kept.get("run_time") if isinstance(kept, dict)
            else None}


def unchanged(record):
    """The skills whose previous version would install the same as the version under test (`installed`)."""
    return sorted(name for name in record["previous"]
                  if installed(record, name, "previous_version") == installed(record, name, "with_skill"))


def proofs(repo, skill_dir, name, kept, read):
    """{arm: `proof`} of a team skill's releases in a round: the release under test, and, with `kept` (the round's
    record of the previous version), the previous one, read as `read` (`rounds.previous`) reads it, by its commit."""
    found = {"with_skill": proof(skill_dir, name)}
    if kept:
        with read(repo, name, kept["commit"], kept["sha256"]) as (folder, _):
            found["previous_version"] = proof(folder, name, skill_dir)
    return found
