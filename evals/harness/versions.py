"""The verified version a plan is held to (doc 12, One setup): the one rule that sets a round beside the skill's
last verified version.

One rule: a skill changed since the last version `evals/results/<skill>.json` records as `verified`, which the plan
runs a task case of, has that version as `previous`, so the comparison is made inside the round on one setup
(`verified`). `rounds.plan` records what it finds in the manifest.

Standard library only.
"""

from pathlib import Path

import results
from rounds import RoundError


def verified(path, repo, found, known_cases):
    """{skill: its last verified version (`results.verified`)} for each skill of the plan with a folder, whose
    cases are `known_cases`. A skill changed since that version that the plan runs a task case of must have it as
    `previous`, so the comparison is made inside the round (doc 12, One setup); an unchanged one, or one run in
    trigger cases only, which compare no versions (`runs.arms`), has no previous arm and stands alone. A version
    with no recorded hash is unknown: it is recorded as such and asks for nothing."""
    found_verified = {}
    for name in sorted(set(known_cases) - set(found["absent"])):
        try:
            last = results.verified(results.recorded(Path(repo) / "evals" / "results", name))
        except results.ResultsError as error:
            raise RoundError(f"{path}: {error}") from None
        if last is None:
            continue
        found_verified[name] = last
        tasks = any(case.kind == "task" for case in known_cases[name].values())  # the test `previous` is held to
        if not tasks or last["sha256"] in (None, found["skills"][name]["sha256"]):
            continue
        if found["previous"].get(name, {}).get("sha256") != last["sha256"]:
            raise RoundError(f"{path}: {name} was verified in round {last['round']} with hash {last['sha256']}, "
                             "and it has changed since, so the plan names that version as previous")
    return found_verified
