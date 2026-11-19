"""The label gate of a round (doc 11, Rounds, results and labels): the labels of 10 · Skills, from the store alone.

One rule: a label is computed by one function (`labels`) from what the round stored: the attempt record, and for
each kept or made run its bundle, its check verdicts and its trusted grades. A rerun on the same store gives the
same label. And a label rests only on settled results: every planned run that is not scored, whatever the reason,
is named, and so is a reference result that is not settled, and either keeps the label at most `inconclusive`.

- A task run passes when every contract expectation of its case passed, fails when one failed, and is not scored
  when one has no trusted answer and none failed (`task_outcome`). A check's verdict decides first; a grader's
  trusted answer decides what no check did, `yes` passing. Only contract expectations count: format ones are the
  skill's own format, which the without-skill arm cannot know, and the done question (`cases.done`) asks what the
  run says, not what it did.
- A task run is a false done when the graders' trusted answer to the done question is `yes` and the run fails.
  Each label gives, per arm, `false_done`: the false dones of the runs where both are decided, and how many are
  not decided.
- A trigger run passes when the skill loaded exactly when the case says it should (`trigger_outcome`). A load the
  host reported (`observed`) and one the adapter inferred from a read of the skill's `SKILL.md` both count, as the
  discovery probe counts them: some hosts, Codex among them, report no skill load of their own. The label names
  how many trigger runs rested on an inferred load only (`inferred_loads`). Only the with-skill arm of a trigger
  case is scored, as only it installs the skill. A trigger case passes when the skill loaded in at least half its
  scored runs if it should trigger, and in fewer than half if it should not. Trigger accuracy is that of the `test`
  split, the `train` split being for tuning a description.
- A planned run is not scored when it is void or empty, or its outcome is not decided. Each is named (`unsettled`).
- A skill the plan gives a previous version (`runs.PREVIOUS`) must be at least as good as it on the same task
  cases: its pass rate not below the previous version's, and its false-done rate not above it (plan decision 2,
  eval-rounds-plan.md). The previous arm's runs count like any other arm's: too few, or a false-done rate with no
  decided run in either arm, keep the label at most `inconclusive`.
- Each skill on each host gets one label (`decide`), with the thresholds of 10 · Skills (`THRESHOLDS`):
  - `incomplete` when the host was not run, the skill has no folder yet (a baseline round, whose label file still
    gives the without-skill arm's pass rate and scored runs per case), or no task case or no test trigger case,
    with every doubt below named too;
  - `inconclusive` when a case has fewer scored runs than `min_runs` in an arm it is scored in, a planned run is not
    scored, an expectation's goldens were missed (each named), the reference host's result is not settled (it was
    not run, or it is itself in doubt), or the skill shows no lift over the baseline;
  - `unsupported` when the task pass rate, the gap to the reference host, the trigger accuracy or the with-skill
    arm's format conformance misses its threshold, or the skill is worse than its previous version, with each gap
    named. Format conformance is a floor on top of the lift, never in its place (`format_gaps`);
  - `verified` otherwise.
- The label file of an attempt is written to `<store>/<round>/labels/<attempt>.json`, through the round's scrub.

Standard library only.
"""

import json
from pathlib import Path

import evidence
import grades
import measures
import prices
from runs import PREVIOUS

THRESHOLDS = {"task_pass_rate": 0.9, "max_gap": 0.10, "trigger_accuracy": 0.9, "min_runs": 3, "min_lift": 0.0,
              "format_conformance": 0.9}
EPSILON = 1e-9


def task_outcome(case, verdicts, answers):
    """(True, False or None, why) of one task run of `case`: `verdicts` are its check verdicts (one per expectation,
    None where it has no check), `answers` its trusted grader answers by question id (`q1` is the first)."""
    counted = [number for number, e in enumerate(case.expectations, start=1) if isinstance(e["source"], dict)]
    if not counted:
        return None, "the case has no contract expectation"
    found = {}
    for number in counted:
        verdict = verdicts[number - 1]
        if verdict is not None and verdict["outcome"] in ("pass", "fail"):
            found[number] = verdict["outcome"] == "pass"
        elif f"q{number}" in answers:
            found[number] = answers[f"q{number}"] == "yes"
        else:
            found[number] = None
    failed = [n for n, passed in found.items() if passed is False]
    if failed:
        return False, f"expectation {failed[0]} failed"
    open_ = [n for n, passed in found.items() if passed is None]
    return (None, f"expectation {open_[0]} has no trusted answer") if open_ else (True, "")


def trigger_outcome(case, log):
    """(passed, inferred) of one with-skill trigger run of `case`: whether the skill loaded exactly when it should,
    and whether only an inferred load says it loaded."""
    sources = {entry.get("source") for entry in log if entry.get("kind") == "skill" and entry.get("name") == case.skill}
    return bool(sources) == bool(case.should_trigger), bool(sources) and "observed" not in sources


def rate(passed):
    """The share of True in `passed`, rounded; None when it is empty."""
    return round(sum(passed) / len(passed), 4) if passed else None


def summary(cases, scored, previous=False, absent=False):
    """The measures of one skill on one host: `cases` are its cases by id, `scored` the outcomes of its scored runs
    by (case id, arm), True or False. With `previous`, the round ran its task cases in the previous version's arm
    too. With `absent`, the skill has no folder yet and the round ran its task cases without it only."""
    tasks = [i for i, case in cases.items() if case.kind == "task"]
    triggers = [i for i, case in cases.items() if case.kind == "trigger" and case.split == "test"]
    with_skill = [o for i in tasks for o in scored.get((i, "with_skill"), [])]
    without = [o for i in tasks for o in scored.get((i, "without_skill"), [])]
    passing = []
    for i in triggers:
        right = scored.get((i, "with_skill"), [])  # each run: did it do what the case says
        if right:  # the skill loaded in at least half the runs of a should-trigger case, in fewer of a should-not
            passing.append(2 * sum(right) >= len(right) if cases[i].should_trigger else 2 * sum(right) > len(right))
    task_arms = ("without_skill",) if absent else ("with_skill", "without_skill") + ((PREVIOUS,) if previous else ())
    runs = {f"{i}, {arm}": len(scored.get((i, arm), [])) for i in tasks for arm in task_arms}
    runs.update({f"{i}, with_skill": len(scored.get((i, "with_skill"), [])) for i in triggers})
    task_rate, baseline = rate(with_skill), rate(without)
    earlier = {"previous_pass_rate": rate([o for i in tasks for o in scored.get((i, PREVIOUS), [])])} \
        if previous else {}
    earlier.update({"absent": True} if absent else {})
    return {"task_pass_rate": task_rate, "baseline_pass_rate": baseline, **earlier,
            "lift": None if None in (task_rate, baseline) else round(task_rate - baseline, 4),
            "trigger_accuracy": rate(passing), "task_cases": len(tasks), "trigger_cases": len(triggers),
            "runs": runs}


def missing(measures):
    """What is missing for any label: the skill itself (a baseline round of a skill with no folder yet), a task case
    or a test trigger case."""
    return ["the skill: no folder yet, a baseline round"] * bool(measures.get("absent")) + [
        f"{kind}: none" for kind, count in (("task cases", measures["task_cases"]),
                                            ("test trigger cases", measures["trigger_cases"])) if not count]


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
    if missing(measures):
        return {"label": "incomplete", "gaps": missing(measures) + doubted}
    gaps, task_rate, trigger = [], measures["task_pass_rate"], measures["trigger_accuracy"]
    if task_rate is not None and task_rate < thresholds["task_pass_rate"] - EPSILON:
        gaps.append(f"task pass rate {task_rate:.0%} below {thresholds['task_pass_rate']:.0%}")
    if reference is not None and task_rate is not None \
            and reference["task_pass_rate"] - task_rate > thresholds["max_gap"] + EPSILON:
        gaps.append(f"task pass rate {reference['task_pass_rate'] - task_rate:.0%} below the reference host")
    if trigger is not None and trigger < thresholds["trigger_accuracy"] - EPSILON:
        gaps.append(f"trigger accuracy {trigger:.0%} below {thresholds['trigger_accuracy']:.0%}")
    gaps += earlier + formatted
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
    scored, unsettled, inferred, false_done = {}, {}, {}, {}
    for made in gates["run"]["outcome"]:
        case = cases[(made["skill"], made["case"])]
        if case.kind == "trigger" and made["arm"] != "with_skill":
            continue
        name = f"{made['case']}, {made['arm']}, run {made['number']}"
        if made["status"] not in ("kept", "made"):
            unsettled.setdefault((made["host"], made["skill"]), []).append(f"{name}: not scored ({made['status']})")
            continue
        run_folder = folder / "runs" / made["key"]
        if case.kind == "trigger":
            record_, _ = evidence.load(run_folder / "bundle")
            passed_, only_inferred = trigger_outcome(case, record_["log"])
            slot = (made["host"], made["skill"])
            inferred[slot] = inferred.get(slot, 0) + bool(only_inferred)
        else:
            verdicts = json.loads((run_folder / "checks.json").read_text())["verdicts"]
            graded = folder / "grades" / attempt / "runs" / f"{made['key']}.json"
            answers = json.loads(graded.read_text())["answers"] if graded.is_file() else {}
            passed_, why = task_outcome(case, verdicts, answers)
            said = [answers.get(f"q{n}") for n, e in enumerate(case.expectations, start=1) if e["source"] == "done"]
            tally = false_done.setdefault((made["host"], made["skill"]), {}).setdefault(
                made["arm"], {"false_done": 0, "decided": 0, "undecided": 0})
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
    found = {"round": record["round"], "attempt": attempt, "commit": record["commit"], "thresholds": THRESHOLDS,
             "reference": grades.REFERENCE, "prices": price_file["date"], "skills": {}}
    rest = measures.measures(folder, attempt, gates, cases, price_file)
    for skill in sorted(record["cases"]):
        own = {i: case for (s, i), case in cases.items() if s == skill}
        unreliable = {f"{name} {question}": why for name, doubts in trust.items() if name.split("/")[0] == skill
                      for question, why in doubts.items() if why is not None}  # name: "<skill>/<case>"
        measured = {host: summary(own, scored.get((host, skill), {}), skill in record.get("previous", {}),
                                  skill in record.get("absent", [])) for host in passed}
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


class LabelError(Exception):
    """The store does not hold what a label is computed from."""


def label_gate(r):
    """The label gate of the round `r` (`gates.Round`): the attempt's label file, written to the store."""
    found = labels(r.folder, r.attempt, r.record, r.cases, prices.load(r.repo))
    path = r.folder / "labels" / f"{r.attempt}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    r.write(path, found)
    return {skill: {host: entry["label"] for host, entry in hosts.items()} for skill, hosts in found["skills"].items()}
