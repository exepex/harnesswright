"""The label file's other measures (doc 11, Rounds, results and labels): what each label rests on, read from the
store the same way the label is.

One rule: a measure counts only what the store holds, and says what it could not count; nothing is estimated.
Each skill on each host gets (`measures`):

- `void_rate`, per arm: the share of tries that were void (`void.json` keeps every void of a slot, a remade one too).
- `grader_agreement`: the share of graded questions the two graders answered the same, over the host's task runs.
- `golden_accuracy`: the share of the skill's graded questions whose goldens the panel got right (the same for
  every host, as goldens are graded once per attempt).
- `faults`: how many of the planted harness faults the fault gate caught on the host; None when the attempt has no
  passed fault gate.
- `inferred_evidence`, per arm: how many expectations of task runs a check left undecidable because the evidence
  it reads is inferred (`checks.decide`).
- `format_conformance`, per arm: the share of decided format expectations of task runs that passed, a check
  deciding first and a trusted grader answer what no check did. It is reported here, never in the pass rate.
- `cost`, per arm: the scored-or-not runs made, their seconds, their token counts by model, and their money at the
  price file (`prices.cost`). A run with no counts, or a model with no price, has no money: the arm's money is None
  and `unpriced` says how many runs had none. A run with no seconds is counted in `untimed`.

Standard library only.
"""

import json

import evidence
import prices
from host import TOKENS


def share(part, whole):
    """`part` of `whole`, rounded; None when `whole` is 0."""
    return round(part / whole, 4) if whole else None


def measures(folder, attempt, gates, cases, price_file):
    """{(host, skill): measures} of the attempt `attempt` of the round in `folder`, whose gates by name are `gates`,
    with the round's `cases` by (skill, case id) and the checked `price_file`."""
    found = {}

    def slot(host, skill):
        return found.setdefault((host, skill), {
            "tries": {}, "voids": {}, "agreed": 0, "asked": 0, "inferred": {}, "format": {}, "cost": {}})

    graded = {run["key"]: run for run in gates["grade"]["outcome"]["runs"]}
    for made in gates["run"]["outcome"]:
        case, arm, here = cases[(made["skill"], made["case"])], made["arm"], slot(made["host"], made["skill"])
        run_folder = folder / "runs" / made["key"]
        voids = len(json.loads((run_folder / "void.json").read_text())["reasons"]) \
            if (run_folder / "void.json").is_file() else 0
        made_now = made["status"] in ("kept", "made")
        here["tries"][arm] = here["tries"].get(arm, 0) + voids + made_now
        here["voids"][arm] = here["voids"].get(arm, 0) + voids
        if not made_now:
            continue
        record, _ = evidence.load(run_folder / "bundle")
        _cost(here["cost"].setdefault(arm, {"runs": 0, "seconds": 0, "untimed": 0, "tokens": {}, "money": 0,
                                            "unpriced": 0}), record, price_file)
        if case.kind != "task":
            continue
        if made["key"] in graded:
            here["agreed"] += graded[made["key"]]["agreed"]
            here["asked"] += graded[made["key"]]["asked"]
        verdicts = json.loads((run_folder / "checks.json").read_text())["verdicts"]
        sheet = folder / "grades" / attempt / "runs" / f"{made['key']}.json"
        answers = json.loads(sheet.read_text())["answers"] if sheet.is_file() else {}
        here["inferred"][arm] = here["inferred"].get(arm, 0) + sum(bool(v and v.get("inferred")) for v in verdicts)
        passed, decided = here["format"].get(arm, (0, 0))
        for number, expectation in enumerate(case.expectations, start=1):
            if expectation["source"] != "format":
                continue
            verdict = verdicts[number - 1]
            if verdict is not None and verdict["outcome"] in ("pass", "fail"):
                passed, decided = passed + (verdict["outcome"] == "pass"), decided + 1
            elif f"q{number}" in answers:
                passed, decided = passed + (answers[f"q{number}"] == "yes"), decided + 1
        here["format"][arm] = (passed, decided)
    goldens = gates["grade"]["outcome"]["goldens"]
    faults = gates["faults"]["outcome"] if gates.get("faults", {}).get("passed") else None
    result = {}
    for (host, skill), here in found.items():
        own = [why for name, questions in goldens.items() if name.split("/")[0] == skill
               for why in questions.values()]  # name: "<skill>/<case>"
        caught = None if faults is None else faults.get(host, [])
        result[(host, skill)] = {
            "void_rate": {arm: share(here["voids"][arm], tries) for arm, tries in sorted(here["tries"].items())},
            "grader_agreement": share(here["agreed"], here["asked"]),
            "golden_accuracy": share(sum(why is None for why in own), len(own)),
            "faults": None if caught is None else {"caught": sum(bool(f["caught"]) for f in caught),
                                                   "planted": len(caught)},
            "inferred_evidence": dict(sorted(here["inferred"].items())),
            "format_conformance": {arm: share(*counts) for arm, counts in sorted(here["format"].items())},
            "cost": {arm: {**cost, "money": None if cost["unpriced"] else round(cost["money"], 6)}
                     for arm, cost in sorted(here["cost"].items())}}
    return result


def _cost(arm, record, price_file):
    """Add the run `record` (a bundle's record) to the cost of its `arm`."""
    arm["runs"] += 1
    if isinstance(record.get("seconds"), (int, float)):
        arm["seconds"] = round(arm["seconds"] + record["seconds"], 3)
    else:
        arm["untimed"] += 1
    tokens = record.get("tokens")
    for model, counts in (tokens or {}).items():
        total = arm["tokens"].setdefault(model, dict.fromkeys(TOKENS, 0))
        for name in TOKENS:
            total[name] += counts[name]
    money = prices.cost(tokens, price_file)
    if money is None:
        arm["unpriced"] += 1
    else:
        arm["money"] += money
