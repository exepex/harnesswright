"""The measuring kit (doc 11, Judges own the measuring kit): its files, its hash, the judges' approval and the
kit check.

One rule: the kit is the files `evals/kit.json` lists under the parts of PARTS, and the list itself. Each listed
path is a file git tracks, or a folder whose tracked files all count. The kit's hash is the manifest digest of those
files. A judge session approves a hash by writing an approval record to the round store, outside the working tree,
where the builder's session cannot write. The kit check refuses unless the record holds the kit's hash, and names
each file that changed since.

Run from the repository root:

    python3 evals/harness/kit.py hash
    python3 evals/harness/kit.py approve --store DIR --judge NAME
    python3 evals/harness/kit.py check --store DIR

Standard library only.
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

import manifest
import skills
from cases import REPO, CaseError

LIST = "evals/kit.json"
# The parts doc 11 names. A part that does not exist yet is added to the list when it does.
PARTS = ("checks", "answer keys", "lint rules", "power table", "probes", "goldens", "grader prompt",
         "fault catalogue")
RECORD = "kit-approval.json"


class KitError(RuntimeError):
    """A kit that cannot be read, or one the judges have not approved, with the reason. The round stops."""


def files(repo=REPO):
    """{repository path: manifest entry} of every file in the kit, the list itself included."""
    repo = Path(repo)
    try:
        parts = json.loads((repo / LIST).read_text())["parts"]
        if not isinstance(parts, dict) or not all(isinstance(p, list) for p in parts.values()):
            raise TypeError("parts is not an object of lists")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise KitError(f"{LIST}: not a kit list: {error}") from None
    wrong = sorted(set(parts) - set(PARTS))
    if wrong or not parts:
        raise KitError(f"{LIST}: the parts {wrong or 'listed'} are not parts of the kit {list(PARTS)}")
    try:
        tracked = set(skills.tracked(repo))
        listed = [LIST] + [path for paths in parts.values() for path in paths]
        found = {}
        for path in listed:
            if not isinstance(path, str) or os.path.normpath(path) != path or path.startswith(("/", "..")):
                raise KitError(f"{LIST}: {path!r} is not a plain repository path")
            inside = [rel for rel in tracked if rel == path or rel.startswith(path + "/")]
            if not inside:
                raise KitError(f"{LIST}: {path} is not a file or folder git tracks")
            for rel in inside:
                skills.tracked_file(repo, rel)  # a regular file in real folders, never a link
                found[rel] = manifest.entry(repo / rel)
        return dict(sorted(found.items()))
    except (CaseError, manifest.Unreadable) as error:
        raise KitError(f"the kit cannot be read: {error}") from None


def digest(repo=REPO):
    """The kit's hash."""
    return manifest.digest(files(repo))


def approve(store, judge, repo=REPO):
    """Write the approval record of the kit as it is now to `store`, for `judge`, read it back, and return it. The
    store must be outside the working tree."""
    folder = _store(store, repo)
    found = files(repo)
    record = {"kit": manifest.digest(found), "files": found, "judge": judge,
              "approved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    if not isinstance(judge, str) or not judge.strip():
        raise KitError("an approval names the judge who gave it")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / RECORD).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    if _read(folder) != record:
        raise KitError(f"{folder / RECORD}: the record read back is not the one written")
    return record


def check(store, repo=REPO):
    """The kit check: return the approved hash, or raise KitError unless the store's approval record holds the hash
    of the kit as it is now, naming each file added, removed or changed since the approval."""
    record = _read(_store(store, repo))
    found = files(repo)
    if record["kit"] == manifest.digest(found):
        return record["kit"]
    approved = record["files"]
    changed = sorted(path for path in set(found) | set(approved) if found.get(path) != approved.get(path))
    raise KitError(f"the kit differs from the one {record['judge']} approved at {record['approved_at']}: "
                   f"{', '.join(changed) or 'the same files, under another hash'}")


def _store(store, repo):
    folder = Path(os.path.realpath(store))
    root = Path(os.path.realpath(repo))
    if folder == root or root in folder.parents:
        raise KitError(f"{store}: the round store must be outside the working tree")
    return folder


def _read(folder):
    try:
        record = json.loads((folder / RECORD).read_text())
        shape = {"kit": str, "files": dict, "judge": str, "approved_at": str}
        if set(record) != set(shape) or not all(isinstance(record[k], t) for k, t in shape.items()):
            raise ValueError(f"its fields are not exactly {sorted(shape)}")
    except FileNotFoundError:
        raise KitError(f"{folder}: no judge has approved a kit in this store") from None
    except (OSError, ValueError) as error:
        raise KitError(f"{folder / RECORD}: not an approval record: {error}") from None
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(prog="kit.py", description="The measuring kit's hash, approval and check.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("hash", help="print the kit's hash and its files")
    approving = commands.add_parser("approve", help="write the judges' approval record of the kit as it is now")
    checking = commands.add_parser("check", help="refuse unless the store's approval holds the kit's hash")
    for sub in (approving, checking):
        sub.add_argument("--store", required=True, help="the round store, outside the working tree")
    approving.add_argument("--judge", required=True, help="the judge giving the approval")
    args = parser.parse_args(argv)
    try:
        if args.command == "hash":
            found = files()
            print(manifest.digest(found))
            print("\n".join(found))
        elif args.command == "approve":
            print(approve(args.store, args.judge)["kit"])
        else:
            print(check(args.store))
    except KitError as error:
        print(f"kit: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
