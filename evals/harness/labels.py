"""The label gate of a round (doc 11, Rounds, results and labels): the labels of 10 · Skills, from the store alone.

One rule: a label is computed by one function (`labels`) from what the round stored: the attempt record, and for
each kept or made run its bundle, its check verdicts and its trusted grades. A rerun on the same store gives the
same label. And a label rests only on settled results: every planned run that is not scored, whatever the reason,
is named, and so is a reference result that is not settled, and either keeps the label at most `inconclusive`.
A task run's outcome and a skill's measures are `verdicts.py`'s, and a trigger run's outcome is `triggers.py`'s.

- A task run is a false done when the graders' trusted answer to the done question is `yes` and the run fails.
  Each label gives, per arm, `false_done`: the false dones of the runs where both are decided, and how many are
  not decided.
- A planned run is not scored when it is void, empty or not loaded (a pinned run with no proven load, doc 12), or
  its outcome is not decided. Each is named (`unsettled`), and so is each case and arm whose pinned runs never
  loaded. The pinned-load rate per arm comes with the other measures (`measures.measures`).
- A skill the plan gives a previous version (`runs.PREVIOUS`) must be at least as good as it on the same task
  cases: its pass rate not below the previous version's, and its false-done rate not above it (plan decision 2,
  eval-rounds-plan.md). The previous arm's runs count like any other arm's: too few, or a false-done rate with no
  decided run in either arm, keep the label at most `inconclusive`.
- Pressure situations (doc 11): every with-skill run of a situation case must pass, and the skill's cases
  must cover each situation `evals/situations.json` lists for it.
- Each skill on each host gets one label (`decide`), with the thresholds of 10 · Skills (`THRESHOLDS`):
  - `incomplete` when the host was not run, the skill has no folder yet (a baseline round, whose label file still
    gives the without-skill arm's pass rate and scored runs per case), or no task case the pass rate counts or no
    test trigger case, or no case of a situation the skill's list names (or no list), with every doubt below
    named too;
  - `inconclusive` when a case has fewer scored runs than `min_runs` in an arm it is scored in, a planned run is not
    scored, an expectation's goldens were missed (each named), the reference host's result is not settled (it was
    not run, or it is itself in doubt), or the skill shows no lift over the baseline;
  - `unsupported` when the task pass rate, the gap to the reference host, the trigger accuracy or the with-skill
    arm's format conformance misses its threshold, a with-skill run of a situation case failed, or the skill is
    worse than its previous version, with each gap named. Format conformance is a floor on top of the lift, never
    in its place (`format_gaps`);
  - `verified` otherwise.
- The label file of an attempt is written to `<store>/<round>/labels/<attempt>.json`, through the round's scrub. It
  records each skill's setup (`setups.setup`), the one fingerprint two results must share to be compared.

Standard library only.
"""

import json
from pathlib import Path

import evidence
import grades
import measures
import prices
import setups
import triggers
import verdicts
from cases import SKILL_ONLY
from runs import PREVIOUS

THRESHOLDS = {"task_pass_rate": 0.9, "max_gap": 0.10, "trigger_accuracy": 0.9, "min_runs": 3, "min_lift": 0.0,
              "format_conformance": 0.9}
EPSILON = 1e-9


def missing(measures):
    """What is missing for any label: the skill itself (a baseline round of a skill with no folder yet), a task case,
    a test trigger case, or a case of each situation `evals/situations.json` lists for the skill (doc 11)."""
    listed = measures.get("situations_listed")
    return ["the skill: no folder yet, a baseline round"] * bool(measures.get("absent")) + [
        f"{kind}: none" for kind, count in (("task cases", measures["task_cases"]),
                                            ("test trigger cases", measures["trigger_cases"])) if not count] + (
        ["situations: the skill is not in evals/situations.json"] if listed is None else
        [f"situation {name}: no case" for name in measures.get("uncovered", [])])


def doubts(measures, unsettled, false_done, thresholds=THRESHOLDS):
    """Why a result is not settled, the one list both a label and the reference host's settlement rest on: each
    case and arm with too few scored runs, each `unsettled` reason, and each doubt against the previous version
    (`versus`, from the `false_done` tally of each arm)."""
    least = thresholds["min_runs"]
    return [f"{slot}: {count} scored run(s), {least} needed" for slot, count in sorted(measures["runs"].items())
            if count < least] + list(unsettled) + versus(measures, false_done)[1]


def versus(measures, false_done):
    """(gaps, doubts) of one skill against its previous version, when `measures` (`summary`) has one:
    `false_done` holds the false-done tally of each arm (`labels`)."""
    if "previous_pass_rate" not in measures:
        return [], []
    gaps, doubted, now, before = [], [], measures["task_pass_rate"], measures["previous_pass_rate"]
    if None not in (now, before) and now < before - EPSILON:
        gaps.append(f"task pass rate {now:.0%} below the previous version's {before:.0%}")
    tallies = [false_done.get(arm, {"false_done": 0, "decided": 0}) for arm in ("with_skill", PREVIOUS)]
    if any(not t["decided"] for t in tallies):
        doubted.append("false-done rate: no decided run in the with-skill or the previous version's arm")
    elif tallies[0]["false_done"] / tallies[0]["decided"] > tallies[1]["false_done"] / tallies[1]["decided"] + EPSILON:
        gaps.append(f"false-done rate {tallies[0]['false_done']} of {tallies[0]['decided']} above the previous "
                    f"version's {tallies[1]['false_done']} of {tallies[1]['decided']}")
    return gaps, doubted


def format_gaps(measures, thresholds=THRESHOLDS):
    """(gaps, doubts) of the with-skill arm's format conformance in `measures` (the label's measures, with
    `format_conformance` of `measures.measures`). A format expectation no check or trusted answer decided counts as
    not passed. No format answer at all, or no format count, is a doubt: the floor was not measured."""
    tally = (measures.get("format_conformance") or {}).get("with_skill")
    asked = tally["decided"] + tally["undecided"] if tally else 0
    if not asked:
        return [], ["format conformance: no format expectation was asked in the with-skill arm"]
    if tally["passed"] / asked < thresholds["format_conformance"] - EPSILON:
        return [f"format conformance {tally['passed'] / asked:.0%} below {thresholds['format_conformance']:.0%} "
                f"({tally['passed']} of {asked}, {tally['undecided']} undecided)"], []
    return [], []


def floor_gaps(measures):
    """The floor of each pressure situation: every with-skill run of its cases passes."""
    return [f"situation {name}: {tally['runs'] - tally['passed']} of {tally['runs']} with-skill runs failed"
            for name, group in sorted(measures.get("situations", {}).items())
            if name != "none" and (tally := group.get("with_skill")) and tally["passed"] < tally["runs"]]


def decide(measures, unsettled, reference=None, reference_doubt=None, thresholds=THRESHOLDS, false_done=None):
    """{"label", "gaps"} of one skill on one host from its `measures` (`summary`) and `unsettled`, the named reasons
    its result is in doubt (runs not scored, goldens missed). For a host other than the reference host, `reference`
    is the reference host's measures when its result is settled, and `reference_doubt` says why it is not.
    `false_done` is the false-done tally of each arm, for the comparison with a previous version (`versus`).
    `measures` holds the with-skill arm's format conformance too, for its floor (`format_gaps`)."""
    earlier = versus(measures, false_done or {})[0]
    formatted, unmeasured = format_gaps(measures, thresholds)
    doubted = doubts(measures, unsettled, false_done or {}, thresholds) + ([reference_doubt] if reference_doubt else [])
    doubted += unmeasured
    floor = floor_gaps(measures)
    if missing(measures):  # a failed floor is named even here, so a trial round still shows it
        return {"label": "incomplete", "gaps": missing(measures) + doubted + floor}
    gaps, task_rate, trigger = [], measures["task_pass_rate"], measures["trigger_accuracy"]
    if task_rate is not None and task_rate < thresholds["task_pass_rate"] - EPSILON:
        gaps.append(f"task pass rate {task_rate:.0%} below {thresholds['task_pass_rate']:.0%}")
    if reference is not None and task_rate is not None \
            and reference["task_pass_rate"] - task_rate > thresholds["max_gap"] + EPSILON:
        gaps.append(f"task pass rate {reference['task_pass_rate'] - task_rate:.0%} below the reference host")
    if trigger is not None and trigger < thresholds["trigger_accuracy"] - EPSILON:
        gaps.append(f"trigger accuracy {trigger:.0%} below {thresholds['trigger_accuracy']:.0%}")
    gaps += earlier + formatted
    gaps += floor
    if doubted:
        return {"label": "inconclusive", "gaps": doubted + gaps}
    if gaps:
        return {"label": "unsupported", "gaps": gaps}
    if measures["lift"] <= thresholds["min_lift"] + EPSILON:
        return {"label": "inconclusive", "gaps": [
            f"no lift over the baseline ({task_rate:.0%} with the skill, {measures['baseline_pass_rate']:.0%} "
            "without)"]}
    return {"label": "verified", "gaps": []}


def labels(folder, attempt, record, cases, price_file):
    """The label file of attempt `attempt` of the round in `folder` (`<store>/<round>`), whose manifest is
    `record`, with the round's `cases` by (skill, case id) and the checked `price_file`: every number in it read
    from the store, with the other measures of `measures`."""
    gates = {gate["gate"]: gate for gate in json.loads((folder / "attempts" / f"{attempt}.json").read_text())["gates"]}
    for needed in ("probe", "run", "grade"):
        if not gates.get(needed, {}).get("passed"):
            raise LabelError(f"attempt {attempt}: its {needed} gate did not pass")
    passed = gates["probe"]["outcome"]["passed"]
    not_run = gates["probe"]["outcome"]["not run"]
    trust = gates["grade"]["outcome"]["goldens"]
    drift = {}  # each host's tools and drift record, as the probe gate pinned it
    for host in passed:
        try:
            drift[host] = json.loads((folder / "drift" / f"{host}.json").read_text())
        except (OSError, ValueError) as error:
            raise LabelError(f"{host}: the store holds no tools and drift record: {error}") from None
    scored, unsettled, inferred, by_case, pins = {}, {}, {}, {}, {}
    for made in gates["run"]["outcome"]:
        case = cases[(made["skill"], made["case"])]
        if case.kind == "trigger" and made["arm"] != "with_skill":
            continue
        name = f"{made['case']}, {made['arm']}, run {made['number']}"
        if made.get("pinned"):  # the statuses of each case and arm's pinned runs
            pins.setdefault((made["host"], made["skill"]), {}).setdefault(f"{made['case']}, {made['arm']}",
                                                                         set()).add(made["status"])
        if made["status"] not in ("kept", "made"):
            unsettled.setdefault((made["host"], made["skill"]), []).append(f"{name}: not scored ({made['status']})")
            continue
        run_folder = folder / "runs" / made["key"]
        if case.kind == "trigger":
            record_, _ = evidence.load(run_folder / "bundle")
            passed_, only_inferred = triggers.trigger_outcome(case, record_["log"])
            slot = (made["host"], made["skill"])
            inferred[slot] = inferred.get(slot, 0) + bool(only_inferred)
        else:
            checked = json.loads((run_folder / "checks.json").read_text())["verdicts"]
            graded = folder / "grades" / attempt / "runs" / f"{made['key']}.json"
            answers = json.loads(graded.read_text())["answers"] if graded.is_file() else {}
            passed_, why = verdicts.task_outcome(case, checked, answers)
            said = [answers.get(f"q{n}") for n, e in enumerate(case.expectations, start=1) if e["source"] == "done"]
            tally = by_case.setdefault((made["host"], made["skill"]), {}).setdefault(
                (made["case"], made["arm"]), {"false_done": 0, "decided": 0, "undecided": 0})
            if passed_ is None or said != ["yes"] and said != ["no"]:
                tally["undecided"] += 1
            else:
                tally["decided"] += 1
                tally["false_done"] += said == ["yes"] and passed_ is False
        if passed_ is None:
            unsettled.setdefault((made["host"], made["skill"]), []).append(f"{name}: not scored ({why})")
            continue
        scored.setdefault((made["host"], made["skill"]), {}).setdefault((made["case"], made["arm"]), []).append(
            passed_)
    for slot, statuses in pins.items():
        unsettled.setdefault(slot, []).extend(f"{where}: no loaded run" for where, seen in sorted(statuses.items())
                                              if "not loaded" in seen and not seen & {"kept", "made"})
    false_done = {slot: _tally(per_case, lambda i, s=slot[1]: not _skill_only(record, s, i))
                  for slot, per_case in by_case.items()}  # per arm, the cases a plain agent can fail
    found = {"round": record["round"], "attempt": attempt, "commit": record["commit"], "thresholds": THRESHOLDS,
             "reference": grades.REFERENCE, "prices": price_file["date"], "skills": {},
             "setups": {skill: setups.setup(record, skill, {i: c for (s, i), c in cases.items() if s == skill},
                                            drift) for skill in sorted(record["cases"])}}
    rest = measures.measures(folder, attempt, gates, cases, price_file)
    for skill in sorted(record["cases"]):
        own = {i: case for (s, i), case in cases.items() if s == skill}
        unreliable = {f"{name} {question}": why for name, doubts in trust.items() if name.split("/")[0] == skill
                      for question, why in doubts.items() if why is not None}  # name: "<skill>/<case>"
        measured = {host: verdicts.summary(own, scored.get((host, skill), {}), skill in record.get("previous", {}),
                                           skill in record.get("absent", []), record.get("situations", {}).get(skill))
                    for host in passed}
        for host in passed:  # each situation's false dones, per arm
            for group in measured[host]["situations"].values():
                for arm, tally in _tally(by_case.get((host, skill), {}), group["cases"].__contains__).items():
                    group[arm]["false_done"] = measures.share(tally["false_done"], tally["decided"], **tally)
        doubted = {host: unsettled.get((host, skill), []) + [f"{name}: goldens missed ({why})"
                                                             for name, why in sorted(unreliable.items())]
                   for host in passed}
        reference, reference_doubt = None, f"the reference host {grades.REFERENCE} was not run"
        if grades.REFERENCE in measured:
            reference_doubt = None
            if missing(measured[grades.REFERENCE]) or doubts(measured[grades.REFERENCE], doubted[grades.REFERENCE],
                                                             false_done.get((grades.REFERENCE, skill), {})):
                reference_doubt = f"the reference host {grades.REFERENCE}'s result is not settled"
            else:
                reference = measured[grades.REFERENCE]
        found["skills"][skill] = {}
        for host in sorted(record["hosts"]):
            entry = {"model": record["hosts"][host]["model"],
                     "host_version": record["hosts"][host]["version"]["version"]}
            if host not in measured:
                entry.update(label="incomplete", gaps=[f"not run: {why}" for why in not_run.get(host, ["no probe"])])
            else:
                other = host != grades.REFERENCE
                entry.update(measured[host], **rest.get((host, skill), {}),
                             inferred_loads=inferred.get((host, skill), 0),
                             false_done={arm: measures.share(tally["false_done"], tally["decided"], **tally)
                                         for arm, tally in sorted(false_done.get((host, skill), {}).items())},
                             **decide({**measured[host], **rest.get((host, skill), {})}, doubted[host],
                                      reference if other else None,
                                      reference_doubt if other else None,
                                      false_done=false_done.get((host, skill), {})))
            found["skills"][skill][host] = entry
    return found


def _skill_only(record, skill, case_id):
    return record.get("situations", {}).get(skill, {}).get("cases", {}).get(case_id) in SKILL_ONLY


def _tally(per_case, keep):
    """{arm: false-done tally} summed over the cases of `per_case` ({(case id, arm): tally}) that `keep` keeps."""
    found = {}
    for (case_id, arm), tally in sorted(per_case.items()):
        if keep(case_id):
            total = found.setdefault(arm, {"false_done": 0, "decided": 0, "undecided": 0})
            for key in total:
                total[key] += tally[key]
    return found


class LabelError(Exception):
    """The store does not hold what a label is computed from."""


def label_gate(r):
    """The label gate of the round `r` (`gates.Round`): the attempt's label file, written to the store."""
    found = labels(r.folder, r.attempt, r.record, r.cases, prices.load(r.repo))
    path = r.folder / "labels" / f"{r.attempt}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    r.write(path, found)
    return {skill: {host: entry["label"] for host, entry in hosts.items()} for skill, hosts in found["skills"].items()}
