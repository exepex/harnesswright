"""The visibility audit: runs inside a run's jail before the host starts, and checks the jail against its one list
of mounts (doc 11, Containment).

`contain.py` runs this file's source after `manifest.py`'s, as one `python3 -I -c` program text, in the same jail
and environment the host gets. The spec comes as JSON on standard input, so neither the code nor the spec is a file
the run can read. It prints one JSON object: `problems`, `env` (the keys the process was given) and `filled` (the
manifest digest of each folder the harness fills, which `contain.py` compares with what it put there).

The checks, each from the one list:

- every folder the jail creates (the root, the folders on the way to a mount, and an empty `/tmp`) holds exactly
  the next steps to the mounts below it, and each mount is there as the kind the list says;
- no process outside the run is visible: `/proc` holds only the audit and the processes it runs under;
- the jail's network holds only loopback, so the gate's socket is the only way out;
- no canary token is in any mount marked for scanning; a file that cannot be read is a problem, so a scan is never
  partial.

Standard library only. It never writes anything.
"""

import json
import os
import stat
import sys

if "digest" not in globals():  # imported for tests, not run after manifest.py's source
    from manifest import Unreadable, digest, manifest


def view(spec, problems):
    """Check every folder the jail creates against the mounts below it."""
    mounts = {m["path"]: m for m in spec["mounts"]}
    created = ["/"] + [path for path, m in mounts.items() if m["how"] == "tmpfs"]
    while created:
        folder = created.pop()
        below = [p for p in mounts if p != folder and _inside(p, folder)]
        want = {os.path.relpath(p, folder).split("/")[0] for p in below}
        try:
            have = set(os.listdir(folder))
        except OSError as error:
            problems.append(f"{folder} cannot be listed: {error.strerror}")
            continue
        if have != want:
            problems.append(f"{folder} holds {sorted(have - want)} beyond the mounts and lacks {sorted(want - have)}")
        for name in sorted(have & want):
            path = os.path.join(folder, name)
            mount = mounts.get(path)
            if mount is None:
                if os.path.islink(path) or not os.path.isdir(path):
                    problems.append(f"{path} is on the way to a mount but is not a folder")
                else:
                    created.append(path)
            elif mount["how"] == "link":
                if not os.path.islink(path) or os.readlink(path) != mount["source"]:
                    problems.append(f"{path} is not the link to {mount['source']} the list says")
            elif mount["how"] == "tmpfs":
                continue  # listed in `created` already
            elif mount["how"] == "socket":
                if not stat.S_ISSOCK(os.lstat(path).st_mode):
                    problems.append(f"{path} is not the gate's socket the list says")
            elif os.path.islink(path) or not os.path.exists(path):
                problems.append(f"{path} is not mounted as the list says")


def _inside(path, folder):
    return path.startswith(folder.rstrip("/") + "/")


def processes(problems):
    """The only processes this run can see are itself and the processes it runs under, up to the jail's first."""
    allowed, pid = set(), os.getpid()
    while pid > 0 and pid not in allowed:
        allowed.add(pid)
        with open(f"/proc/{pid}/stat") as handle:
            pid = int(handle.read().rpartition(")")[2].split()[1])
    seen = {int(name) for name in os.listdir("/proc") if name.isdigit()}
    if seen - allowed:
        problems.append(f"{len(seen - allowed)} processes outside the run are visible in /proc")


def network(problems, table="/proc/net/dev"):
    """The jail's only network interface is loopback."""
    with open(table) as handle:
        names = sorted(line.split(":")[0].strip() for line in handle.readlines()[2:])
    if names != ["lo"]:
        problems.append(f"the jail's network has interfaces {names}, not only loopback")


def canaries(spec, problems):
    """No planted token in any mount marked for scanning."""
    tokens = [token.encode() for token in spec["tokens"]]
    if not tokens:
        return
    for mount in (m for m in spec["mounts"] if m["scan"]):
        for path in _files(mount["path"], problems):
            try:
                data = os.readlink(path).encode() if os.path.islink(path) else open(path, "rb").read()
            except OSError as error:
                problems.append(f"{path} cannot be read to scan it: {error.strerror}")
                continue
            if any(token in data for token in tokens):
                problems.append(f"a canary token is in {path}")


def _files(top, problems):
    if not os.path.isdir(top) or os.path.islink(top):
        yield top
        return

    def refuse(error):
        problems.append(f"{error.filename} cannot be listed to scan it: {error.strerror}")

    for root, dirs, names in os.walk(top, onerror=refuse):
        yield from (os.path.join(root, name) for name in names)
        yield from (os.path.join(root, name) for name in dirs if os.path.islink(os.path.join(root, name)))


def environment():
    """The keys the process was started with, read from the kernel, before Python adds any of its own."""
    with open("/proc/self/environ", "rb") as handle:
        return sorted(item.split(b"=", 1)[0].decode() for item in handle.read().split(b"\0") if item)


def audit(spec):
    problems, filled = [], {}
    view(spec, problems)
    for mount in (m for m in spec["mounts"] if m["filled"]):
        try:
            filled[mount["path"]] = digest(manifest(mount["path"]))
        except Unreadable as error:
            problems.append(str(error))
    processes(problems)
    network(problems)
    canaries(spec, problems)
    return {"problems": problems, "env": environment(), "filled": filled}


if __name__ == "__main__":
    print(json.dumps(audit(json.loads(sys.stdin.read()))))
