"""Powers: what a run can do (doc 11, Powers).

One rule: the power table below is the only statement of what a run may do, and the powers probe proves the jail
gives exactly that. The jail enforces the table for the host and its commands alike, so each host's own sandbox is
turned off and nothing is left for a host to refuse.

`PROBE` runs inside the run's jail as one `python3 -I -c` program text, like the audit, so no harness file is
mounted for it. It tries every row and prints one JSON object: {row: true when the action worked}. A task-run write
to the world removes the file again, so the world is unchanged. `probe` compares the outcome with the table.

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
import json, os, socket, sys

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

def write(folder):
    path = os.path.join(folder, ".hw-power-probe")
    with open(path, "x") as handle:
        handle.write("probe\n")
    os.unlink(path)

def connect():
    socket.create_connection(("1.1.1.1", 443), timeout=5).close()

def through_gate(host):
    gate = socket.create_connection(("127.0.0.1", spec["port"]), timeout=10)
    gate.sendall(f"CONNECT {host}:443 HTTP/1.1\r\n\r\n".encode())
    status = gate.makefile("rb").readline().split()[1:2]
    gate.close()
    if status == [b"403"] or not status:
        raise OSError("refused by the gate")

found = {
    "read the world": works(lambda: read(spec["world"])),
    "read system folders": works(lambda: read("/usr/bin")),
    "read scratch": bool(spec["scratch"]) and works(lambda: read(spec["scratch"])),
    "write the world": works(lambda: write(spec["world"])),
    "write scratch": bool(spec["scratch"]) and works(lambda: write(spec["scratch"])),
    "write the private home": works(lambda: write(spec["home"])),
    "write temp": works(lambda: write(os.environ["TMPDIR"])) and works(lambda: write("/tmp")),
    "write outside the run": any(works(lambda f=f: write(f)) for f in ("/", "/usr", "/etc", "/run")),
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


def probe(run, program="python3"):
    """Run the powers probe in `run`'s jail (a `contain.Containment`) and return what it found. Raise PowersError
    with every row that differs from the table."""
    spec = {"world": str(run.world), "scratch": str(run.scratch) if run.scratch else None, "home": str(run.home),
            "port": contain.gate.PORT, "model_host": run.hosts[0] if run.hosts else None}
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

