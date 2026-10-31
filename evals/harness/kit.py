"""The measuring kit: everything that decides a label besides the agent (doc 11, Judges own the measuring kit).

Its hash covers the lint, the containment and its audit, the power table and probes, the evidence format, the
adapters that configure each host to the table, the fault catalogue, and (as later pull requests add them) the
checks with their answer keys, the goldens and the grader prompt. Independent judges approve one hash: each judge
writes its own verdict to `STORE/kit-approvals/<hash>/<judge>.json`. A round refuses to start unless at least three
judges approved the current hash and none asked for changes.

    python3 evals/harness/kit.py hash
    python3 evals/harness/kit.py check --store STORE
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import REPO, sha256_file, tree_hash  # noqa: E402

KIT = ("evals/harness/*.py", "evals/harness/tests/**/*.py", "evals/runner/seal.py", "adapters/*/adapter.py",
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


def approval_dir(store, digest):
    """Each judge writes its own verdict here, as `<judge>.json`; the builder writes nothing in it."""
    return Path(store) / "kit-approvals" / digest


def check(store, repo=REPO, min_judges=MIN_JUDGES):
    """Return the judges' verdicts on the current kit, or raise KitError saying why it is not approved.

    A verdict is {"judge", "kit_sha256", "files", "verdict": "approve" or "changes", "findings"}.
    """
    digest = kit_hash(repo)
    folder = approval_dir(store, digest)
    verdicts = [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))] if folder.is_dir() else []
    if not verdicts:
        raise KitError(f"no judge has approved kit {digest[:12]} ({folder})")
    current = files(repo)
    for verdict in verdicts:
        if verdict.get("kit_sha256") != digest or verdict.get("files") != current:
            raise KitError(f"the verdict of {verdict.get('judge')} names another kit")
    judges = {v.get("judge") for v in verdicts}
    approving = [v for v in verdicts if v.get("verdict") == "approve"]
    if len(judges) < min_judges or len(approving) != len(verdicts):
        raise KitError(f"the kit needs {min_judges} independent judges who all approve; {len(approving)} of "
                       f"{len(verdicts)} verdicts approve, from {len(judges)} judges")
    return {"kit_sha256": digest, "judges": verdicts}


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
