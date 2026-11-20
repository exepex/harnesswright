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
  decided run in either arm, keep the label at most `inconclusive` (`doubts`).
- Each measure is decided `pass`, `fail` or `too close` by one rule (`judge`, doc 12, Verdicts): rates are means of
  per-case rates, and a split case, whose runs disagree, moves one run toward the skill's best and its worst
  (`mean`). A measure fails when it fails even at its best and passes when it passes even at its worst.
- Pressure situations (doc 11): a case of a situation a plain agent cannot fail (`cases.SKILL_ONLY`) runs with the
  skill only and counts in no pass rate, lift or false-done rate. Each label gives every situation's pass and
  false-done counts per arm, and the cases with no situation apart (`situations`). Every with-skill run of a
  situation case must pass: one failed run makes that situation `too close`, a second makes it fail (`floors`); and
  the skill's cases must cover each situation `evals/situations.json` lists for it (`missing`).
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
    fails, a situation's floor fails, or the skill is worse than its previous version, with each gap named. Format
    conformance is a floor on top of the lift, never in its place;
  - `too close` when a measure or floor is too close, a team skill's lift included; never `verified`;
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


def as_runs(per_case):
    """{case: [[passed, asked]] per run} of `per_case` ({case: [passed, scored]} runs): each run passed or failed."""
    return {i: [[1, 1]] * passed + [[0, 1]] * (count - passed) for i, (passed, count) in per_case.items()}


def mean(cases, move=0):
    """The mean of per-case rates of `cases` ({case: [[passed, asked] of each run]}), each case's rate its passed
    items over its asked items; None with no case. A split case is one whose runs disagree. At its best
    (`move` 1) one run of each split case, its worst, passes whole; at its worst (`move` -1) one, its best, fails
    whole: a run for a pass rate, the items of one run for format conformance. Unsplit cases never move."""
    rates = []
    for runs in cases.values():
        runs = [run for run in runs if run[1]]
        if not runs:
            continue
        passed, asked = sum(run[0] for run in runs), sum(run[1] for run in runs)
        if move and len({run[0] / run[1] for run in runs}) > 1:
            moved = (min if move > 0 else max)(runs, key=lambda run: run[0] / run[1])
            passed += moved[1] - moved[0] if move > 0 else -moved[0]
        rates.append(passed / asked)
    return sum(rates) / len(rates) if rates else None


def _round(value):
    return None if value is None else round(value, 4)


def judge(at, meets):
    """The verdict of one measure (doc 12, Verdicts), the one rule for every measure: {"verdict", "value", "best",
    "worst"}, where `at(move)` is the measure as measured (0), at its best for the skill (1) and at its worst (-1),
    and `meets(value)` says whether a value passes. It fails when it fails even at its best, passes when it passes
    even at its worst, and is `too close` otherwise. None when the measure has no value."""
    value, best, worst = at(0), at(1), at(-1)
    if None in (value, best, worst):
        return None
    verdict = "fail" if not meets(best) else "pass" if meets(worst) else "too close"
    return {"verdict": verdict, "value": _round(value), "best": _round(best), "worst": _round(worst)}


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
    task_arms = ("without_skill",) if absent else ("with_skill",) + ("without_skill",) * (kind != "internal") + (
        (PREVIOUS,) if previous else ())
    arms_of = {i: ("with_skill",) if situated.get(i) in SKILL_ONLY else task_arms for i in tasks}
    runs = {f"{i}, {arm}": len(scored.get((i, arm), [])) for i in tasks for arm in arms_of[i]}
    per_case = {arm: {i: [sum(scored.get((i, arm), [])), len(scored.get((i, arm), []))] for i in pooled}
                for arm in task_arms}  # [passed, scored] runs of each case the rates pool
    task_rate, baseline = (_round(mean(as_runs(per_case.get(arm, {})))) for arm in ("with_skill", "without_skill"))
    earlier = {"previous_pass_rate": _round(mean(as_runs(per_case[PREVIOUS])))} if previous else {}
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
            "task_cases": len(pooled), "runs": runs, "per_case": per_case, "situations_listed": listed,
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
    case and arm with too few scored runs, each `unsettled` reason, and, for a round with a previous version, an arm
    with no decided false-done answer (`false_done`, each case and arm's tally of the cases a plain agent can fail)."""
    least, pooled = thresholds["min_runs"], _pooled(false_done)
    undecided = "previous_pass_rate" in measures and any(not pooled[arm]["decided"] for arm in ("with_skill", PREVIOUS))
    return [f"{slot}: {count} scored run(s), {least} needed" for slot, count in sorted(measures["runs"].items())
            if count < least] + list(unsettled) + [
        "false-done rate: no decided run in the with-skill or the previous version's arm"] * undecided


def _pooled(false_done):
    """{arm: the false-done tally summed over cases} of `false_done` ({(case id, arm): tally})."""
    found = {arm: {"false_done": 0, "decided": 0} for arm in ("with_skill", PREVIOUS)}
    for (_, arm), tally in (false_done or {}).items():
        found.setdefault(arm, {"false_done": 0, "decided": 0})
        for key in ("false_done", "decided"):
            found[arm][key] += tally[key]
    return found


def _less(one, other):
    return None if None in (one, other) else one - other


def judged(measures, reference=None, false_done=None, thresholds=THRESHOLDS):
    """{measure: its verdict (`judge`)} of one skill on one host from its `measures` (`summary`, with the format
    items of `measures.measures`): the task pass rate, the gap to the `reference` host's pass rate, format
    conformance, a team skill's lift, and against a previous version its pass rate and its false-done rate
    (`false_done` by case and arm). A measure that reads two arms moves the with-skill arm toward its best and the
    other toward its worst, and back (doc 12, Verdicts)."""
    per_case, found = measures.get("per_case", {}), {}
    ran, base, before = (as_runs(per_case.get(arm, {})) for arm in ("with_skill", "without_skill", PREVIOUS))
    at_least = lambda floor: lambda value: value >= floor - EPSILON  # noqa: E731
    found["task pass rate"] = judge(lambda m: mean(ran, m), at_least(thresholds["task_pass_rate"]))
    if reference is not None:
        found["gap to the reference host"] = judge(lambda m: _less(reference["task_pass_rate"], mean(ran, m)),
                                                   lambda value: value <= thresholds["max_gap"] + EPSILON)
    formats = (measures.get("format_runs") or {}).get("with_skill")
    if formats:
        found["format conformance"] = judge(lambda m: mean(formats, m), at_least(thresholds["format_conformance"]))
    if measures.get("kind") != "internal":
        found["lift"] = judge(lambda m: _less(mean(ran, m), mean(base, -m)),
                              lambda value: value > thresholds["min_lift"] + EPSILON)
    if PREVIOUS in per_case:
        found["previous pass rate"] = judge(lambda m: _less(mean(ran, m), mean(before, -m)), at_least(0))
        good = {arm: {i: [[1, 1]] * (t["decided"] - t["false_done"]) + [[0, 1]] * t["false_done"]
                      for (i, a), t in (false_done or {}).items() if a == arm} for arm in ("with_skill", PREVIOUS)}
        found["previous false-done rate"] = judge(lambda m: _less(mean(good["with_skill"], m),
                                                                  mean(good[PREVIOUS], -m)), at_least(0))
    return {name: verdict for name, verdict in found.items() if verdict is not None}


def floors(measures):
    """{situation: its floor's verdict}: every with-skill run of its cases must pass. One failed run makes it `too
    close`, a second makes it fail (owner decision, 2026-11-20)."""
    return {f"situation {name}": {"verdict": ("pass", "too close")[failed] if failed < 2 else "fail",
                                  "failed": failed, "runs": tally["runs"]}
            for name, group in sorted(measures.get("situations", {}).items())
            if name != "none" and (tally := group.get("with_skill"))
            for failed in [tally["runs"] - tally["passed"]]}


def _gap(name, verdict, measures, false_done, thresholds):
    """The named gap of a measure or floor that did not pass."""
    if name.startswith("situation "):
        return f"{name}: {verdict['failed']} of {verdict['runs']} with-skill runs failed" + (
            " (too close)" if verdict["verdict"] == "too close" else "")
    if verdict["verdict"] == "too close":
        return (f"{name} too close: {verdict['value']:.0%} as measured, {verdict['worst']:.0%} at worst, "
                f"{verdict['best']:.0%} at best")
    value, tally = verdict["value"], (measures.get("format_conformance") or {}).get("with_skill") or {}
    pooled = _pooled(false_done)
    if name == "task pass rate":
        return f"task pass rate {value:.0%} below {thresholds['task_pass_rate']:.0%}"
    if name == "gap to the reference host":
        return f"task pass rate {value:.0%} below the reference host"
    if name == "format conformance":
        return (f"format conformance {value:.0%} below {thresholds['format_conformance']:.0%} ({tally['passed']} of "
                f"{tally['decided'] + tally['undecided']}, {tally['undecided']} undecided)")
    if name == "lift":
        return (f"no lift over the baseline ({measures['task_pass_rate']:.0%} with the skill, "
                f"{measures['baseline_pass_rate']:.0%} without)")
    if name == "previous pass rate":
        return (f"task pass rate {measures['task_pass_rate']:.0%} below the previous version's "
                f"{measures['previous_pass_rate']:.0%}")
    return (f"false-done rate {pooled['with_skill']['false_done']} of {pooled['with_skill']['decided']} above the "
            f"previous version's {pooled[PREVIOUS]['false_done']} of {pooled[PREVIOUS]['decided']}")


def decide(measures, unsettled, reference=None, reference_doubt=None, thresholds=THRESHOLDS, false_done=None):
    """{"label", "gaps", "verdicts"} of one skill on one host from its `measures` (`summary`) and `unsettled`, the
    named reasons its result is in doubt (runs not scored, goldens missed). For a host other than the reference host,
    `reference` is the reference host's measures when its result is settled, and `reference_doubt` says why it is
    not. `false_done` is each case and arm's false-done tally, for the comparison with a previous version.
    `verdicts` names each measure's and floor's verdict, with its best and worst values (`judged`, `floors`)."""
    found = {**judged(measures, reference, false_done, thresholds), **floors(measures)}
    gaps = {verdict: [_gap(name, v, measures, false_done, thresholds) for name, v in found.items()
                      if v["verdict"] == verdict and (name != "lift" or verdict == "too close")]
            for verdict in ("fail", "too close")}
    tally = (measures.get("format_conformance") or {}).get("with_skill") or {}
    unasked = not tally.get("decided", 0) + tally.get("undecided", 0)  # the format floor was not measured
    doubted = doubts(measures, unsettled, false_done, thresholds) + ([reference_doubt] if reference_doubt else []) + [
        "format conformance: no format expectation was asked in the with-skill arm"] * unasked
    floor = [gap for gap in gaps["fail"] + gaps["too close"] if gap.startswith("situation ")]
    named = lambda label, listed: {"label": label, "gaps": listed, "verdicts": found}  # noqa: E731
    if missing(measures):  # a failed floor is named even here, so a trial round still shows it
        return named("incomplete", missing(measures) + doubted + floor)
    if doubted:
        return named("inconclusive", doubted + gaps["fail"] + gaps["too close"])
    if gaps["fail"]:
        return named("unsupported", gaps["fail"])
    if gaps["too close"]:  # never verified
        return named("too close", gaps["too close"])
    if found.get("lift", {}).get("verdict") == "fail":  # no lift is not a failure of the skill
        return named("inconclusive", [_gap("lift", found["lift"], measures, false_done, thresholds)])
    return named("verified", [])
