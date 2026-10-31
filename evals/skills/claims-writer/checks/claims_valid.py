#!/usr/bin/env python3
"""Expectation check: exactly one claims file was written under a run folder, and it passes the
skill's own structure check against the project it describes.

Argument: the run's output folder. Exit 0 when the expectation holds.
"""

import subprocess
import sys
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[4] / "skills" / "claims-writer" / "scripts" / "claims_check.py"


def main(outputs):
    found = sorted(p for p in Path(outputs).rglob("*.md")
                   if p.parent.name == "claims" and p.parents[2].name == "runs" and p.parents[3].name == ".harness")
    if len(found) != 1:
        print(f"want exactly one claims file under .harness/runs/*/claims/, found {len(found)}: {found}")
        return 1
    claims = found[0]
    project = claims.parents[4]
    done = subprocess.run([sys.executable, str(CHECKER), "check", "--repo", str(project), str(claims)],
                          capture_output=True, text=True)
    print(f"{claims.relative_to(outputs)}:\n{done.stdout}{done.stderr}")
    return done.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
