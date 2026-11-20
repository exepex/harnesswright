"""The task verdict of one skill on one host (doc 11, Rounds, results and labels): its run outcomes and its measures.

One rule: a skill's measures on one host are computed by one function (`summary`) from the outcomes of its scored
runs, each task run's outcome by one function (`task_outcome`).

- A task run passes when every contract expectation of its case passed, fails when one failed, and is not scored
  when one has no trusted answer and none failed (`task_outcome`). A check's verdict decides first; a grader's
  trusted answer decides what no check did, `yes` passing. Only contract expectations count: format ones are the
  skill's own format, which the without-skill arm cannot know, and the done question (`cases.done`) asks what the
  run says, not what it did.
- Pressure situations (doc 11): a case of a situation a plain agent cannot fail (`cases.SKILL_ONLY`) runs with the
  skill only and counts in no pass rate, lift or false-done rate. Each label gives every situation's pass and
  false-done counts per arm, and the cases with no situation apart (`situations`).
- Trigger accuracy is the share of test trigger cases that passed (`triggers.passing`).

Standard library only.
"""

import triggers as triggers_
from cases import SKILL_ONLY
from runs import PREVIOUS


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


def summary(cases, scored, previous=False, absent=False, situations=None):
    """The measures of one skill on one host: `cases` are its cases by id, `scored` the outcomes of its scored runs
    by (case id, arm), True or False. With `previous`, the round ran its task cases in the previous version's arm
    too. With `absent`, the skill has no folder yet and the round ran its task cases without it only. `situations`
    is the manifest's record of the skill's situations (`rounds.plan`): a case a plain agent cannot fail
    (`SKILL_ONLY`) counts in no pass rate or lift, and each situation is reported apart."""
    situated = (situations or {}).get("cases", {})
    tasks = [i for i, case in cases.items() if case.kind == "task"]
    pooled = [i for i in tasks if situated.get(i) not in SKILL_ONLY]
    triggers, passing = triggers_.passing(cases, scored)  # the test trigger cases, and which passed
    with_skill = [o for i in pooled for o in scored.get((i, "with_skill"), [])]
    without = [o for i in pooled for o in scored.get((i, "without_skill"), [])]
    task_arms = ("without_skill",) if absent else ("with_skill", "without_skill") + ((PREVIOUS,) if previous else ())
    arms_of = {i: ("with_skill",) if situated.get(i) in SKILL_ONLY else task_arms for i in tasks}
    runs = {f"{i}, {arm}": len(scored.get((i, arm), [])) for i in tasks for arm in arms_of[i]}
    runs.update({f"{i}, with_skill": len(scored.get((i, "with_skill"), [])) for i in triggers})
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
    return {"task_pass_rate": task_rate, "baseline_pass_rate": baseline, **earlier,
            "lift": None if None in (task_rate, baseline) else round(task_rate - baseline, 4),
            "trigger_accuracy": rate(passing), "task_cases": len(pooled), "trigger_cases": len(triggers),
            "runs": runs, "situations_listed": listed,
            "uncovered": sorted(set(listed or ()) - set(situated.values())),
            "situations": report}

