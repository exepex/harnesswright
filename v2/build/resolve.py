"""The standards reader's command: resolve an application's rule layers (plan/b01-plan.md part e).

Standard library only. Shipped in each release skill's scripts/ beside rulebook.py, reach.py and copyform.py, and
imports only them. Parts e1a, e1b and e2 fill it in; until then it prints its usage and stops.

Run: python3 resolve.py --repo REPO --run RUN-ID --date YYYY-MM-DD
"""

import sys

USAGE = "usage: resolve.py --repo REPO --run RUN-ID --date YYYY-MM-DD (not built yet: B0.1 part e1)"


def main(argv=None):
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
