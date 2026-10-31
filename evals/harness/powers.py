"""Powers: what a run can do (doc 11, Powers).

One rule: the power table below is the only statement of what a run may do, and the powers probe proves the jail
gives exactly that. The jail enforces the table for the host and its commands alike, so each host's own sandbox is
turned off and nothing is left for a host to refuse.

`PROBE` runs inside the run's jail as one `python3 -I -c` program text, like the audit, so no harness file is mounted
for it. It tries every row and prints one JSON object: {row: true when the action worked}. Each write makes a file
with a unique name and removes it again, so the world is unchanged. "Write outside the run" reads the jail's own mount
table from the kernel: any mount it lets the run write must be one of the places the table lets the mode write (the
private home, `/tmp` and `/dev/shm`, the world and scratch in task runs, and the probe-output folder in probe runs), a
device file, or a kernel view of the jail (proc, devpts). So it covers every mount and everything below one, never a
list of places to try. "Connect directly" never trusts a failed connection alone: the harness holds a listener open on
the machine's loopback, which any jail sharing the machine's network reaches, and the jail must also have its own
network namespace with loopback only. A model host counts as reached only when the gate opens a tunnel to one of the
allowed hosts. `probe` compares the outcome with the table.

Standard library only.
"""

import json
import os
import socket
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

# The kinds of host tool a run may have, in both modes. A sub-agent runs in the same jail, so it has the same
# powers. A `wait` tool has no power at all: it sleeps, waits for its own command or sub-agent, or asks a question
# no one answers in a run. Each adapter names its host's tools by kind (`host.CONTRACT`); a tool of any other kind
# stops the round.
TOOLS = ("read", "write", "command", "skill", "agent", "wait")

PROBE = r'''
import json, os, re, socket, stat, sys, tempfile

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
        before = os.stat(path)
        handle, name = tempfile.mkstemp(dir=path, prefix=".hw-power-probe-")
        os.close(handle)
        os.unlink(name)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))  # the world keeps its normalised times
    else:
        open(path, "r+b").close()

def writable_mounts():
    """Every mount the kernel lets the run write that the table does not: read from the jail's own mount table, so
    no mount, and nothing below a mount, is left out. A mount may be writable only when it is one of the places the
    table lets this mode write, a device file (such as /dev/null), or a kernel view of the jail itself (proc,
    devpts)."""
    found = []
    with open("/proc/self/mountinfo", "rb") as handle:
        for line in handle:
            fields = line.split()
            # The kernel escapes only space, tab, newline and backslash, as octal; every other byte is the path's own.
            point = os.fsdecode(re.sub(rb"\\([0-7]{3})", lambda m: bytes([int(m.group(1), 8)]), fields[4]))
            kind = fields[fields.index(b"-") + 1].decode()
            fields = [field.decode(errors="replace") for field in fields]
            if "rw" not in fields[5].split(","):
                continue
            if point in spec["writable"] or kind in ("proc", "devpts"):
                continue
            if stat.S_ISCHR(os.stat(point).st_mode):
                continue
            found.append(point)
    return found

def connect():
    socket.create_connection(tuple(spec["direct"]), timeout=5).close()

def shares_network():
    """True when the jail has any network of the machine's: the harness's own network namespace, an interface other
    than loopback, or a connection to the listener the harness holds open on the machine's loopback."""
    with open("/proc/net/dev") as handle:
        interfaces = [line.split(":")[0].strip() for line in handle.readlines()[2:]]
    return os.stat("/proc/self/ns/net").st_ino == spec["network"] or interfaces != ["lo"] or works(connect)

def gate_answer(host):
    gate = socket.create_connection(("127.0.0.1", spec["port"]), timeout=10)
    gate.sendall(f"CONNECT {host}:443 HTTP/1.1\r\n\r\n".encode())
    status = gate.makefile("rb").readline().split()[1:2]
    gate.close()
    return status

def through_gate(host):
    if gate_answer(host) != [b"200"]:  # only an open tunnel counts
        raise OSError("no tunnel through the gate")

found = {
    "read the world": works(lambda: read(spec["world"])),
    "read system folders": works(lambda: read("/usr/bin")),
    "read scratch": bool(spec["scratch"]) and works(lambda: read(spec["scratch"])),
    "write the world": works(lambda: write(spec["world"])),
    "write scratch": bool(spec["scratch"]) and works(lambda: write(spec["scratch"])),
    "write the private home": works(lambda: write(spec["home"])),
    "write temp": all(works(lambda f=f: write(f)) for f in (os.environ["TMPDIR"], "/tmp", "/dev/shm")),
    "write outside the run": bool(writable_mounts()),
    "connect directly": shares_network(),
    # Only the gate's own refusal counts: any other answer, such as a 502 from upstream, means it passed the host on.
    "reach a host off the allow list": gate_answer("off-the-list.invalid") != [b"403"],
    "reach a model host through the gate": any(works(lambda h=h: through_gate(h)) for h in spec["model_hosts"]),
}
found["writable mounts off the table"] = writable_mounts()
found["nonce"] = spec.get("nonce")  # proves the output came from this run's probe, not a guess
print(json.dumps(found))
'''


class PowersError(RuntimeError):
    """The jail does not give exactly the powers of the table. The host is `not run` for the round."""


def expected(mode):
    """{row: must it work} for a run in `mode`."""
    column = {"trigger": 0, "task": 1}[mode]
    return {row: modes[column] for row, modes in TABLE.items()}


def spec(run):
    """What the probe needs to know about `run`, besides the address of the listener it must not reach."""
    may = expected(run.mode)
    writable = [str(run.home), "/tmp", "/dev/shm"] + ([str(run.world)] if may["write the world"] else []) + \
        ([str(run.scratch)] if may["write scratch"] and run.scratch else []) + \
        ([str(run.probe_out)] if run.probe_out else [])  # the probe-output folder, in probe runs only
    return {"world": str(run.world), "scratch": str(run.scratch) if run.scratch else None, "home": str(run.home),
            "writable": writable, "port": contain.gate.PORT, "model_hosts": list(run.hosts),
            "network": os.stat("/proc/self/ns/net").st_ino}


def check(run, output, stderr="", nonce=None):
    """The probe's `output` (its printed JSON) for `run`, compared with the table. Return what it found, or raise
    PowersError with every row that differs. `nonce` is the one the spec gave, when it gave one."""
    try:
        found = json.loads(output)
    except json.JSONDecodeError:
        raise PowersError(f"the powers probe did not run: {stderr.strip()[-400:]}") from None
    if not isinstance(found, dict):
        raise PowersError(f"the powers probe printed {output[:200]!r}")
    if found.pop("nonce", None) != nonce:
        raise PowersError("the powers output is not from this run's probe")
    off = found.pop("writable mounts off the table", [])
    wrong = [f"{row}: {'works' if found.get(row) else 'does not work'}, the table says it "
             f"{'must' if must else 'must not'}"
             for row, must in expected(run.mode).items() if found.get(row) != must]
    if off:
        wrong.append(f"writable mounts off the table: {off}")
    if wrong:
        raise PowersError("; ".join(wrong))
    return found


def probe(run, program="python3"):
    """Run the powers probe in `run`'s jail (a `contain.Containment`) and return what it found. Raise PowersError
    with every row that differs from the table."""
    command = run.jail([contain.PYTHON, "-I", "-c", PROBE], program=program)
    # A control the probe can always reach unless the jail has its own network: so a refused connection proves it.
    with socket.create_server(("127.0.0.1", 0)) as listener, run.gate():
        given = {**spec(run), "direct": listener.getsockname()}
        result = subprocess.run(command, input=json.dumps(given), capture_output=True, text=True, env=run.env,
                                timeout=120)
    return check(run, result.stdout, result.stderr)
