"""The task verdict of one skill on one host (doc 11, Rounds, results and labels): its measures and its label.

One rule: a label is decided by one function (`decide`) from the skill's measures (`summary`) and the named reasons
its result is in doubt, by the thresholds of 10 · Skills (`THRESHOLDS`).

- A task run passes when every contract expectation of its case passed, fails when one failed, and is not scored
  when one has no trusted answer and none failed (`task_outcome`). A check's verdict decides first; a grader's
  trusted answer decides what no check did, `yes` passing. Only contract expectations count: format ones are the
  skill's own format, which the without-skill arm cannot know, and the done question (`cases.done`) asks what the
  run says, not what it did.
- A skill the plan gives a previous version (`runs.PREVIOUS`) must be at least as good as it on the same task
  cases: its pass rate not below the previous version's, and its false-done rate not above it (plan decision 2,
  eval-rounds-plan.md). The previous arm's runs count like any other arm's: too few, or a false-done rate with no
  decided run in either arm, keep the label at most `inconclusive` (`versus`).
- Pressure situations (doc 11): a case of a situation a plain agent cannot fail (`cases.SKILL_ONLY`) runs with the
  skill only and counts in no pass rate, lift or false-done rate. Each label gives every situation's pass and
  false-done counts per arm, and the cases with no situation apart (`situations`). Every with-skill run of a
  situation case must pass (`floor_gaps`), and the skill's cases must cover each situation `evals/situations.json`
  lists for it (`missing`).
- The task label never reads a trigger case: trigger accuracy is the trigger label's (`triggers.label`), a line of
  its own (doc 12, Proven use).
- The label reads the skill's kind (doc 12, Labels by kind). A team skill is scored by its lift over a plain agent
  on top of the floors; an internal skill ran no without-skill arm, so it has no lift and is scored by the floors.
- Each skill on each host gets one label (`decide`):
  - `incomplete` when the host was not run, the skill has no kind declared, no folder yet (a baseline round, whose
    label file still gives the without-skill arm's pass rate and scored runs per case), or no task case the pass
    rate counts, or no case of a situation the skill's list names (or no list), with every doubt below named too;
  - `inconclusive` when a case has fewer scored runs than `min_runs` in an arm it is scored in, a planned run is not
    scored, an expectation's goldens were missed (each named), the reference host's result is not settled (it was
    not run, or it is itself in doubt) (`doubts`), or a team skill shows no lift over the baseline;
  - `unsupported` when the task pass rate, the gap to the reference host or the with-skill arm's format conformance
    misses its threshold, a with-skill run of a situation case failed, or the skill is worse than its previous
    version, with each gap named. Format conformance is a floor on top of the lift, never in its place
    (`format_gaps`);
  - `verified` otherwise.

Standard library only.
"""

from cases import SKILL_ONLY
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


def rate(passed):
    """The share of True in `passed`, rounded; None when it is empty."""
    return round(sum(passed) / len(passed), 4) if passed else None


def summary(cases, scored, previous=False, absent=False, situations=None, kind=None):
    """The measures of one skill on one host: `cases` are its cases by id, `scored` the outcomes of its scored runs
    by (case id, arm), True or False. With `previous`, the round ran its task cases in the previous version's arm
    too. With `absent`, the skill has no folder yet and the round ran its task cases without it only. `situations`
    is the manifest's record of the skill's situations (`rounds.plan`): a case a plain agent cannot fail
    (`SKILL_ONLY`) counts in no pass rate or lift, and each situation is reported apart. `kind` is the skill's
    declared kind (`cases.kinds`): an internal skill ran no without-skill arm, so it has no baseline and no lift.
    Trigger cases are the trigger label's (`triggers.label`), never the task label's."""
    situated = (situations or {}).get("cases", {})
    tasks = [i for i, case in cases.items() if case.kind == "task"]
    pooled = [i for i in tasks if situated.get(i) not in SKILL_ONLY]
    with_skill = [o for i in pooled for o in scored.get((i, "with_skill"), [])]
    without = [o for i in pooled for o in scored.get((i, "without_skill"), [])]
    task_arms = ("without_skill",) if absent else ("with_skill",) + ("without_skill",) * (kind != "internal") + (
        (PREVIOUS,) if previous else ())
    arms_of = {i: ("with_skill",) if situated.get(i) in SKILL_ONLY else task_arms for i in tasks}
    runs = {f"{i}, {arm}": len(scored.get((i, arm), [])) for i in tasks for arm in arms_of[i]}
    task_rate, baseline = rate(with_skill), rate(without)
    earlier = {"previous_pass_rate": rate([o for i in pooled for o in scored.get((i, PREVIOUS), [])])} \
        if previous else {}
    earlier.update({"absent": True} if absent else {})
    groups = {}  # each situation's cases, and the cases with none apart, so earlier rounds stay comparable
    for i in tasks:
        groups.setdefault(situated.get(i) or "none", []).append(i)
    report = {}
    for name, ids in sorted(groups.items()):
        report[name] = {"cases": ids}
        for arm in arms_of[ids[0]]:  # a situation's cases share their arms
            outcomes = [o for i in ids for o in scored.get((i, arm), [])]
            report[name][arm] = {"passed": sum(outcomes), "runs": len(outcomes)}
    listed = (situations or {}).get("listed")
    return {"kind": kind, "task_pass_rate": task_rate, "baseline_pass_rate": baseline, **earlier,
            "lift": None if None in (task_rate, baseline) else round(task_rate - baseline, 4),
            "task_cases": len(pooled), "runs": runs, "situations_listed": listed,
            "uncovered": sorted(set(listed or ()) - set(situated.values())),
            "situations": report}


def missing(measures):
    """What is missing for any label: the skill's declared kind (doc 12, Skill kinds), the skill itself (a baseline
    round of a skill with no folder yet), a task case, or a case of each situation `evals/situations.json` lists for
    the skill (doc 11)."""
    listed = measures.get("situations_listed")
    return ["kind: none declared in evals/kinds.json"] * (measures.get("kind") is None) + [
        "the skill: no folder yet, a baseline round"] * bool(measures.get("absent")) + [
        "task cases: none"] * (not measures["task_cases"]) + (
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
    gaps, task_rate = [], measures["task_pass_rate"]
    if task_rate is not None and task_rate < thresholds["task_pass_rate"] - EPSILON:
        gaps.append(f"task pass rate {task_rate:.0%} below {thresholds['task_pass_rate']:.0%}")
    if reference is not None and task_rate is not None \
            and reference["task_pass_rate"] - task_rate > thresholds["max_gap"] + EPSILON:
        gaps.append(f"task pass rate {reference['task_pass_rate'] - task_rate:.0%} below the reference host")
    gaps += earlier + formatted
    gaps += floor
    if doubted:
        return {"label": "inconclusive", "gaps": doubted + gaps}
    if gaps:
        return {"label": "unsupported", "gaps": gaps}
    if measures["kind"] != "internal" and measures["lift"] <= thresholds["min_lift"] + EPSILON:  # no lift inside
        return {"label": "inconclusive", "gaps": [
            f"no lift over the baseline ({task_rate:.0%} with the skill, {measures['baseline_pass_rate']:.0%} "
            "without)"]}
    return {"label": "verified", "gaps": []}

