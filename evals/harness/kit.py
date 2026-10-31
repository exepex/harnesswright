"""The measuring kit: everything that decides a label besides the agent (doc 11, Judges own the measuring kit).

Its hash covers the lint, the containment and its audit, the power table and probes, the evidence format, the
adapters that configure each host to the table, the fault catalogue, and (as later pull requests add them) the
checks with their answer keys, the goldens and the grader prompt. Independent judges approve one hash. A round
refuses to start unless the store holds an approval of the current hash.

    python3 evals/harness/kit.py hash
    python3 evals/harness/kit.py check --store STORE
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import REPO, sha256_file, tree_hash  # noqa: E402

KIT = ("evals/harness/audit.py", "evals/harness/cases.py", "evals/harness/contain.py", "evals/harness/evidence.py",
       "evals/harness/hostrun.py", "evals/harness/lint.py", "evals/harness/powers.py", "evals/harness/probes.py",
       "evals/harness/world.py", "evals/harness/tests/**/*.py", "evals/runner/seal.py", "adapters/*/adapter.py",
       "evals/faults/**/*",
       "evals/checks/**/*", "evals/goldens/**/*", "evals/grader/**/*")
MIN_JUDGES = 3


class KitError(RuntimeError):
    """The kit has no matching approval. The round does not start."""


def files(repo=REPO):
    """{path: sha256} of every kit file."""
    repo = Path(repo)
    found = {}
    for pattern in KIT:
        for path in sorted(repo.glob(pattern)):
            if path.is_file() and "__pycache__" not in path.parts:
                found[path.relative_to(repo).as_posix()] = sha256_file(path)
    return found


def kit_hash(repo=REPO):
    return tree_hash(files(repo))


def approval_path(store, digest):
    return Path(store) / "kit-approvals" / f"{digest}.json"


def check(store, repo=REPO, min_judges=MIN_JUDGES):
    """Return the approval record of the current kit, or raise KitError saying why there is none."""
    digest = kit_hash(repo)
    path = approval_path(store, digest)
    if not path.is_file():
        raise KitError(f"no approval of kit {digest[:12]} in {Path(store) / 'kit-approvals'}")
    record = json.loads(path.read_text())
    if record.get("kit_sha256") != digest:
        raise KitError("the approval record names another kit")
    approving = [j for j in record.get("judges", []) if j.get("verdict") == "approve"]
    if len(approving) < min_judges or len(approving) != len(record.get("judges", [])):
        raise KitError(f"the kit needs {min_judges} independent judges who all approve; the record has "
                       f"{len(approving)} of {len(record.get('judges', []))}")
    if set(record.get("files", {})) != set(files(repo)):
        raise KitError("the approval record lists other files than the kit")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("hash", "files", "check"))
    parser.add_argument("--store")
    args = parser.parse_args(argv)
    if args.action == "hash":
        print(kit_hash())
    elif args.action == "files":
        print(json.dumps(files(), indent=1))
    else:
        if not args.store:
            parser.error("check needs --store")
        try:
            record = check(args.store)
        except KitError as error:
            print(f"kit not approved: {error}")
            return 1
        print(f"kit {record['kit_sha256'][:12]} approved by {len(record['judges'])} judges")
    return 0


if __name__ == "__main__":
    sys.exit(main())
