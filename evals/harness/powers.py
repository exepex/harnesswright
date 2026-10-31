"""Powers: what a run can do (doc 11, Powers).

One rule: the power table below is the only statement of what a run may do, and the powers probe proves the jail
gives exactly that. The jail enforces the table for the host and its commands alike, so each host's own sandbox is
turned off and nothing is left for a host to refuse.

`PROBE` runs inside the run's jail as one `python3 -I -c` program text, like the audit, so no harness file is
mounted for it. It tries every row and prints one JSON object: {row: true when the action worked}. Each write makes
a file with a unique name and removes it again, so the world is unchanged. "Write outside the run" tries every place
on the run's list of mounts, and every folder the jail creates, outside the one set of places the table lets the
mode write (the private home and temp folders `/tmp` and `/dev/shm`, and the world and scratch in task runs), so it
is worked out from the list and the table, never from a list of places to try. A model host counts
as reached only when the gate opens a tunnel to it. `probe` compares the outcome with the table.

Standard library only.
"""

import json
import subprocess

import contain

# Each row is one action the probe tries, with whether it must work in a trigger run and in a task run.
TABLE = {
    "read the world": (True, True),
    "read system folders": (True, True),
    "read scratch": (False, True),
    "write the world": (False, True),
    "write scratch": (False, True),
    "write the private home": (True, True),
    "write temp": (True, True),
    "write outside the run": (False, False),
    "connect directly": (False, False),
    "reach a host off the allow list": (False, False),
    "reach a model host through the gate": (True, True),
}

PROBE = r'''
import json, os, socket, sys, tempfile

spec = json.loads(sys.stdin.read())

def works(action):
    try:
        action()
        return True
    except OSError:
        return False

def read(folder):
    os.listdir(folder)
    for root, _, names in os.walk(folder):
        for name in names:
            path = os.path.join(root, name)
            if os.path.isfile(path) and not os.path.islink(path):
                with open(path, "rb") as handle:
                    handle.read(1)
                return

def write(path):
    """Create a new file with a unique name in a folder, and remove it; or open a mounted file for writing without
    writing to it."""
    if os.path.isdir(path):
        handle, name = tempfile.mkstemp(dir=path, prefix=".hw-power-probe-")
        os.close(handle)
        os.unlink(name)
    else:
        open(path, "r+b").close()

def read_only_places():
    """Every place on the run's list of mounts, and every folder the jail creates on the way to one, that is not in
    the one set of places the table lets this mode write. So nothing on the list is left untried."""
    mounts = {m["path"]: m["how"] for m in spec["mounts"]}
    allowed = set(spec["writable"])

    def under(folder):
        """The nearest mount that holds a created folder, or None for the jail's own root."""
        holders = [m for m in mounts if folder.startswith(m.rstrip("/") + "/")]
        return max(holders, key=len) if holders else None

    places = [path for path, how in mounts.items() if how not in ("link", "proc") and path not in allowed]
    for path in mounts:
        parent = os.path.dirname(path)
        while parent not in mounts and parent not in places and under(parent) not in allowed:
            places.append(parent)
            if parent == "/":
                break
            parent = os.path.dirname(parent)
    return sorted(places)

def connect():
    socket.create_connection(tuple(spec["direct"]), timeout=5).close()

def through_gate(host):
    gate = socket.create_connection(("127.0.0.1", spec["port"]), timeout=10)
    gate.sendall(f"CONNECT {host}:443 HTTP/1.1\r\n\r\n".encode())
    status = gate.makefile("rb").readline().split()[1:2]
    gate.close()
    if status != [b"200"]:  # only an open tunnel counts
        raise OSError("no tunnel through the gate")

found = {
    "read the world": works(lambda: read(spec["world"])),
    "read system folders": works(lambda: read("/usr/bin")),
    "read scratch": bool(spec["scratch"]) and works(lambda: read(spec["scratch"])),
    "write the world": works(lambda: write(spec["world"])),
    "write scratch": bool(spec["scratch"]) and works(lambda: write(spec["scratch"])),
    "write the private home": works(lambda: write(spec["home"])),
    "write temp": all(works(lambda f=f: write(f)) for f in (os.environ["TMPDIR"], "/tmp", "/dev/shm")),
    "write outside the run": any(works(lambda f=f: write(f)) for f in read_only_places()),
    "connect directly": works(connect),
    "reach a host off the allow list": works(lambda: through_gate("off-the-list.invalid")),
    "reach a model host through the gate":
        bool(spec["model_host"]) and works(lambda: through_gate(spec["model_host"])),
}
print(json.dumps(found))
'''


class PowersError(RuntimeError):
    """The jail does not give exactly the powers of the table. The host is `not run` for the round."""


def expected(mode):
    """{row: must it work} for a run in `mode`."""
    column = {"trigger": 0, "task": 1}[mode]
    return {row: modes[column] for row, modes in TABLE.items()}


def probe(run, program="python3", direct=("1.1.1.1", 443)):
    """Run the powers probe in `run`'s jail (a `contain.Containment`) and return what it found. Raise PowersError
    with every row that differs from the table. `direct` is an address the probe tries to reach without the gate."""
    may = expected(run.mode)
    writable = [str(run.home), "/tmp", "/dev/shm"] + ([str(run.world)] if may["write the world"] else []) + \
        ([str(run.scratch)] if may["write scratch"] and run.scratch else [])
    spec = {"world": str(run.world), "scratch": str(run.scratch) if run.scratch else None, "home": str(run.home),
            "writable": writable,
            "port": contain.gate.PORT, "model_host": run.hosts[0] if run.hosts else None,
            "mounts": [m.spec() for m in run.mounts(program)], "direct": list(direct)}
    command = run.jail([contain.PYTHON, "-I", "-c", PROBE], program=program)
    with run.gate():
        result = subprocess.run(command, input=json.dumps(spec), capture_output=True, text=True, env=run.env,
                                timeout=120)
    try:
        found = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise PowersError(f"the powers probe did not run: {result.stderr.strip()[-400:]}") from None
    wrong = [f"{row}: {'works' if found.get(row) else 'does not work'}, the table says it "
             f"{'must' if must else 'must not'}"
             for row, must in expected(run.mode).items() if found.get(row) != must]
    if wrong:
        raise PowersError("; ".join(wrong))
    return found

