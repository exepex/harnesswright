"""The standards reader's command: resolve an application's rule layers (plan/b01-plan.md part e).

Standard library only. Shipped in each release skill's scripts/ beside rulebook.py, reach.py, copyform.py and
repoprofile.py, and imports only them. It reads the team settings with repoprofile.py, then every layer the run
uses, and stops on any break of docs/design/03-standards.md "Resolving the rules for an application" and
docs/design/07-repo-profile.md, naming the file and line or the layer and folder (HW-AG-09). Part e1a reads and
checks these inputs; parts e1b and e2 combine them and write rules.md and the rules texts.

Run: python3 resolve.py --repo REPO --run RUN-ID --date YYYY-MM-DD
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from repoprofile import PROFILE, RulebookError, read_profile


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    args = parser.parse_args(argv)
    try:
        read_profile(Path(args.repo) / PROFILE)
    except RulebookError as error:
        print(f"resolve stopped: {error}", file=sys.stderr)
        return 1
    print("resolve: profile read; the layers are not read yet (B0.1 part e1a, second pull request)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
