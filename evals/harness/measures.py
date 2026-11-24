"""The label file's other measures (doc 11, Rounds, results and labels): what each label rests on, read from the
store the same way the label is.

One rule: a measure counts only what the store holds, gives its counts beside its share, and names what it left
out; nothing is estimated. A share is `{"rate", ...its counts}`, the rate None when there is nothing to count.
Each skill on each host gets (`measures`):

- `void_rate`, per arm: `voids` of `tries`, every void that `void.json` keeps counting, a remade one too.
- `pinned_load`, per arm with pinned runs (`runs.pinned`, marked by the run gate): the tries that loaded the skill
  (`loaded`, the runs kept or made) of the pinned tries (`tries`), every try not loaded counting too (`runs.misses`).
- `golden_accuracy`: the questions of the skill's graded goldens that the panel answered as settled (`right`) of
  those asked (`asked`), read from each golden's grade record, an extra pass's too, the list trust is read from
  (`grades.golden_records`). The same for every host, as goldens are graded once per attempt and pass.
- `faults`: how many of the planted harness faults the fault gate caught on the host; None when the attempt has no
  passed fault gate.
- `inferred_evidence`, per arm: how many expectations of task runs a check left undecidable because the evidence
  it reads is inferred (`checks.decide`).
- `undecidable_checks`, per arm and check: of the expectations of task runs a check was asked (`ran`), how many it
  left `undecidable` (`undecidable`), for whatever reason, so a check that seldom decides shows up by name.
- `format_conformance`, per arm: the format expectations of task runs that passed (`passed`) of those decided
  (`decided`), a check deciding first and a trusted grader answer what no check did; `undecided` counts the rest.
  It is reported here, never in the pass rate. `format_runs`, per arm and case, gives each run's [passed, asked]
  format items, which the format verdict flips run by run (`verdicts.mean`).
- `cost`, per arm, of the runs made (`runs`): their `seconds` and token counts by model (`tokens`), and their
  `money` at the price file (`prices.cost`). `untimed` runs have no seconds and `uncounted` runs no token counts;
  `unpriced` runs have counts with a model the price file does not price. Either of the last two leaves the arm's
  money None. A voided try keeps no evidence, so its cost is not stored: `voided` says how many tries are left out.
  A try that was not loaded keeps its bundle, so it is costed with the runs, and `not_loaded` says how many of them
  it was.

Standard library only.
"""

import json

import evidence
import grades
import prices
import runs
from host import TOKENS


def share(part, whole, **counts):
    """{"rate": `part` of `whole`, rounded, or None when `whole` is 0, and the `counts`}."""
    return {"rate": round(part / whole, 4) if whole else None, **counts}


def measures(folder, attempt, gates, cases, price_file):
    """{(host, skill): measures} of the attempt `attempt` of the round in `folder`, whose gates by name are `gates`,
    with the round's `cases` by (skill, case id) and the checked `price_file`."""
    found = {}
    for made in gates["run"]["outcome"]:
        case, arm = cases[(made["skill"], made["case"])], made["arm"]
        here = found.setdefault((made["host"], made["skill"]), {"arms": {}})
        own = here["arms"].setdefault(arm, {"tries": 0, "voids": 0, "inferred": 0, "passed": 0, "decided": 0,
                                            "undecided": 0, "cost": dict.fromkeys(COST, 0) | {"tokens": {}},
                                            "pinned": 0, "loaded": 0, "format_runs": {}, "checks": {}})
        run_folder = folder / "runs" / made["key"]
        voids = len(json.loads((run_folder / "void.json").read_text())["reasons"]) \
            if (run_folder / "void.json").is_file() else 0
        made_now = made["status"] in ("kept", "made")
        if made.get("pinned"):
            missed = runs.misses(run_folder)
            own["pinned"], own["loaded"] = own["pinned"] + missed + made_now, own["loaded"] + made_now
            for number in range(missed):  # a try that was not loaded was paid for, and keeps its bundle
                kept = run_folder / runs.UNLOADED_RUNS / str(number) / runs.BUNDLE
                _cost(own["cost"], evidence.load(kept)[0], price_file)
                own["cost"]["not_loaded"] += 1
        own["tries"] += voids + made_now
        own["voids"] += voids
        own["cost"]["voided"] += voids
        if not made_now:
            continue
        record, _ = evidence.load(run_folder / "bundle")
        _cost(own["cost"], record, price_file)
        if case.kind != "task":
            continue
        verdicts = json.loads((run_folder / "checks.json").read_text())["verdicts"]
        sheet = folder / "grades" / attempt / "runs" / f"{made['key']}.json"
        answers = json.loads(sheet.read_text())["answers"] if sheet.is_file() else {}
        own["inferred"] += sum(bool(v and v.get("inferred")) for v in verdicts)
        for v in filter(None, verdicts):
            tally = own["checks"].setdefault(v["check"], [0, 0])
            tally[0], tally[1] = tally[0] + (v["outcome"] == "undecidable"), tally[1] + 1
        before = own["passed"], own["decided"] + own["undecided"]
        for number, expectation in enumerate(case.expectations, start=1):
            if expectation["source"] != "format":
                continue
            verdict = verdicts[number - 1]
            if verdict is not None and verdict["outcome"] in ("pass", "fail"):
                own["passed"], own["decided"] = own["passed"] + (verdict["outcome"] == "pass"), own["decided"] + 1
            elif f"q{number}" in answers:
                own["passed"], own["decided"] = own["passed"] + (answers[f"q{number}"] == "yes"), own["decided"] + 1
            else:
                own["undecided"] += 1
        items = own["passed"] - before[0], own["decided"] + own["undecided"] - before[1]  # this run's format items
        if items[1]:
            own["format_runs"].setdefault(made["case"], []).append(list(items))
    faults = gates["faults"]["outcome"] if gates.get("faults", {}).get("passed") else None
    result = {}
    for (host, skill), here in found.items():
        arms = sorted(here["arms"].items())
        caught = None if faults is None else faults.get(host, [])
        result[(host, skill)] = {
            "void_rate": {arm: share(own["voids"], own["tries"], voids=own["voids"], tries=own["tries"])
                          for arm, own in arms},
            "pinned_load": {arm: share(own["loaded"], own["pinned"], loaded=own["loaded"], tries=own["pinned"])
                            for arm, own in arms if own["pinned"]},
            "golden_accuracy": _goldens(folder / "grades" / attempt, skill),
            "faults": None if caught is None else {"caught": sum(bool(f["caught"]) for f in caught),
                                                   "planted": len(caught)},
            "inferred_evidence": {arm: own["inferred"] for arm, own in arms},
            "undecidable_checks": {arm: {name: share(*tally, undecidable=tally[0], ran=tally[1])
                                         for name, tally in sorted(own["checks"].items())} for arm, own in arms},
            "format_conformance": {arm: share(own["passed"], own["decided"], passed=own["passed"],
                                              decided=own["decided"], undecided=own["undecided"])
                                   for arm, own in arms},
            "format_runs": {arm: own["format_runs"] for arm, own in arms},
            "cost": {arm: _priced(own["cost"]) for arm, own in arms}}
    return result


COST = ("runs", "seconds", "untimed", "uncounted", "unpriced", "money", "voided", "not_loaded")


def _goldens(folder, skill):
    """The golden accuracy of `skill`, from the grade records of its goldens in the attempt's grades `folder`, every
    extra pass's too (`grades.golden_records`)."""
    right = asked = 0
    for path in [p for p in grades.golden_records(folder) if p.parent.parent.name == skill]:
        sheet = json.loads(path.read_text())
        for id_ in sheet["asked"]:
            asked += 1
            right += sheet["answers"].get(id_) == sheet["settled"][id_]
    return share(right, asked, right=right, asked=asked)


def _cost(arm, record, price_file):
    """Add the run `record` (a bundle's record) to the cost of its `arm`."""
    arm["runs"] += 1
    if isinstance(record.get("seconds"), (int, float)):
        arm["seconds"] = round(arm["seconds"] + record["seconds"], 3)
    else:
        arm["untimed"] += 1
    tokens = record.get("tokens")
    if tokens is None:
        arm["uncounted"] += 1
        return
    for model, counts in tokens.items():
        total = arm["tokens"].setdefault(model, dict.fromkeys(TOKENS, 0))
        for name in TOKENS:
            total[name] += counts[name]
    money = prices.cost(tokens, price_file)
    if money is None:
        arm["unpriced"] += 1
    else:
        arm["money"] += money


def _priced(arm):
    """The cost of an arm as the label file keeps it: no money when any run has none."""
    return {**arm, "money": None if arm["uncounted"] or arm["unpriced"] else round(arm["money"], 6)}
