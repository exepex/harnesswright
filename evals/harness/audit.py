"""The visibility audit: runs inside the containment, before the host starts, and lists what a run could see.

`contain.py` runs this file's source with `python3 -I -c` in the same jail and environment the host gets, and
passes the spec as JSON on standard input, so neither the script nor the spec is a file the run can read. It
prints one JSON object: `problems` (empty when the containment holds) and `seen` (what it looked at).

Standard library only. It never writes anything.
"""

import hashlib
import json
import os
import sys


def tree_hash(folder, skip=(".git",)):
    """The same hash as cases.tree_hash(cases.tree(folder, skip)), computed inside the jail."""
    files = {}
    for root, dirs, names in os.walk(folder):
        if root == folder:
            dirs[:] = [d for d in dirs if d not in skip]
        for name in dirs + names:
            path = os.path.join(root, name)
            relative = os.path.relpath(path, folder).replace(os.sep, "/")
            if os.path.islink(path):
                files[relative] = "link:" + os.readlink(path)
            elif os.path.isfile(path):
                with open(path, "rb") as handle:
                    files[relative] = hashlib.sha256(handle.read()).hexdigest()
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def readable(path):
    try:
        if os.path.isdir(path):
            os.listdir(path)
        else:
            with open(path, "rb") as handle:
                handle.read(1)
        return True
    except OSError:
        return False


def holds_token(folder, tokens, limit=20000):
    """The first file under `folder` that holds a canary token, or None. Looks at most at `limit` files."""
    seen = 0
    for root, _dirs, names in os.walk(folder):
        for name in names:
            seen += 1
            if seen > limit:
                return None
            try:
                with open(os.path.join(root, name), "rb") as handle:
                    data = handle.read(1_000_000)
            except OSError:
                continue
            if any(token.encode() in data for token in tokens):
                return os.path.join(root, name)
    return None


def audit(spec):
    problems, seen = [], {}
    extra_env = sorted(set(os.environ) - set(spec["env_allowed"]))
    seen["env"] = sorted(os.environ)
    if extra_env:
        problems.append(f"environment holds variables outside the allow list: {extra_env}")

    top = sorted(os.listdir("/"))
    seen["root"] = top
    stray = [name for name in top if name not in spec["root_allowed"]]
    if stray:
        problems.append(f"/ holds entries outside the allowed set: {stray}")

    for path in spec["forbidden"]:
        if os.path.lexists(path) and readable(path):
            problems.append(f"forbidden path is readable: {path}")

    for path in spec["canary_files"]:
        if readable(path):
            problems.append(f"a planted canary file is readable: {path}")

    for path in spec["masked"]:
        if os.path.isdir(path) and os.listdir(path):
            problems.append(f"masked folder is not empty: {path}")
        elif os.path.isfile(path) and os.path.getsize(path):
            problems.append(f"masked file is not empty: {path}")

    for folder, allowed in spec["only_entries"].items():
        if os.path.isdir(folder):
            extra = sorted(set(os.listdir(folder)) - set(allowed))
            if extra:
                problems.append(f"{folder} holds unexpected entries: {extra}")

    world = spec["world"]
    if tree_hash(world) != spec["world_sha256"]:
        problems.append("the world in the jail is not the built arm")

    for folder in spec["scan"]:
        hit = holds_token(folder, spec["tokens"])
        if hit:
            problems.append(f"a canary token is reachable in {hit}")
    return {"problems": problems, "seen": seen}


if __name__ == "__main__":
    print(json.dumps(audit(json.loads(sys.stdin.read()))))
