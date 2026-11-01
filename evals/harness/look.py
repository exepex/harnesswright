"""Looks: what the harness itself sees from inside a run's jail (doc 11, Harness faults).

One rule: a look is a Python program text the harness runs in the jail of a run, with its host's mounts,
environment and gate, so what it finds is decided by the harness, whatever the host chose to do. It prints JSON.

Standard library only.
"""

import json
import subprocess

import contain

# Given paths on stdin, it prints the ones the jail lets it stat.
SEEN = r"""
import json, os, sys
seen = []
for path in json.load(sys.stdin):
    try:
        os.lstat(path)
    except OSError:
        continue
    seen.append(path)
print(json.dumps(seen))
"""

# It prints the environment the jail gives a program.
ENVIRONMENT = "import json, os\nprint(json.dumps(dict(os.environ)))\n"


def look(contained, program, data=None):
    """What `program` prints in the jail of `contained`, given `data` as JSON on stdin. Raise
    contain.ContainmentError when it does not print JSON."""
    command = contained.jail([contain.PYTHON, "-I", "-c", program], program=contained.adapter.CLI)
    with contained.gate():
        done = subprocess.run(command, input=json.dumps(data), capture_output=True, text=True, env=contained.env,
                              timeout=120)
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError:
        raise contain.ContainmentError(f"the harness could not look inside the jail: "
                                       f"{done.stderr.strip()[-300:]}") from None
