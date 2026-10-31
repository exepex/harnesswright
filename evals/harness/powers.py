"""Equal powers: what a run can do, defined once for each mode (doc 11, Powers).

Each adapter configures its host to this table and removes every host tool outside it, so nothing is left for
the host to refuse. The powers probe runs `PROBE_SOURCE` as a command through the host and compares what it
could do with `expected(mode)`, row by row.
"""

# What a command the host runs may do. "temp" is the run's TMPDIR, which lies inside scratch in a task run.
TABLE = {
    "trigger": {"read": ("world", "system"), "write": (), "commands": True, "network": False},
    "task": {"read": ("world", "scratch", "system"), "write": ("world", "scratch", "temp"), "commands": True,
             "network": False},
}
# Host tools a run may have: reading, searching and writing files, running commands, and loading skills.
# Everything else (sub-agents, web search, browsers, image tools, plugins, MCP servers) is removed.
TOOLS = ("read", "search", "write", "command", "skill")
WRITE_ROWS = ("world", "scratch", "temp", "home", "slash_tmp", "system")
READ_ROWS = ("world", "scratch", "system")


def expected(mode):
    """{row: True or False} that the powers probe must find in `mode`."""
    table = TABLE[mode]
    # A trigger run has no scratch folder, so its scratch rows are not measured.
    keep = [row for row in WRITE_ROWS if not (mode == "trigger" and row == "scratch")]
    rows = {f"read_{row}": row in table["read"] for row in READ_ROWS if row in keep or row == "system"}
    rows.update({f"write_{row}": row in table["write"] for row in keep})
    rows["read_forbidden"] = False
    rows["network_direct"] = table["network"]
    rows["network_proxy"] = table["network"]
    return rows


def compare(mode, found):
    """Every row where the probe's findings differ from the table. Empty means the host has equal powers."""
    want = expected(mode)
    problems = []
    for row, value in want.items():
        if row not in found:
            problems.append(f"{row}: not measured")
        elif bool(found[row]) != value:
            problems.append(f"{row}: {'allowed' if found[row] else 'refused'}, the table says "
                            f"{'allowed' if value else 'refused'}")
    return problems


# Run by the host as `python3 power_probe.py`, from the probe world. It reads its targets from
# `power_probe.json` beside it and prints what it could do as one line starting with MARKER. The probe reads that
# line from the command output the host reported, never from the model's reply.
MARKER = "HW-POWERS "
PROBE_SOURCE = r'''
import json, os, socket, sys, urllib.request
here = os.path.dirname(os.path.abspath(__file__))
spec = json.load(open(os.path.join(here, "power_probe.json")))
found = {}

def can_read(path):
    try:
        if os.path.isdir(path):
            os.listdir(path)
        else:
            open(path, "rb").read(1)
        return True
    except OSError:
        return False

def can_write(folder):
    if not folder:
        return False
    target = os.path.join(folder, ".hw-power-probe")
    try:
        with open(target, "w") as handle:
            handle.write("x")
        os.remove(target)
        return True
    except OSError:
        return False

found["read_world"] = can_read(os.path.join(spec["world"], "README.md"))
found["read_system"] = can_read("/etc/os-release") or can_read("/usr/bin/env")
if spec.get("scratch"):
    found["read_scratch"] = can_read(spec["scratch"])
found["read_forbidden"] = any(can_read(p) for p in spec["forbidden"])
found["write_world"] = can_write(spec["world"])
if spec.get("scratch"):
    found["write_scratch"] = can_write(spec["scratch"])
found["write_temp"] = can_write(os.environ.get("TMPDIR"))
found["write_home"] = can_write(os.environ.get("HOME"))
found["write_slash_tmp"] = can_write("/tmp")
found["write_system"] = can_write("/usr")
try:
    socket.create_connection(("1.1.1.1", 443), timeout=4).close()
    found["network_direct"] = True
except OSError:
    found["network_direct"] = False
try:
    urllib.request.urlopen("https://example.com", timeout=8).read(1)
    found["network_proxy"] = True
except Exception:
    found["network_proxy"] = False
print("HW-POWERS " + json.dumps(found, sort_keys=True))
'''
