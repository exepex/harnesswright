"""The trigger cases of a label (doc 11, Rounds, results and labels): whether the skill loaded when it should.

One rule: a trigger run passes when the skill loaded exactly when its case says it should (`trigger_outcome`), and
a trigger case passes on half its scored runs (`passing`). The trigger label is a line of its own (`label`): the
task label never reads it, and a skill is shipped only when its task label is `verified` and its trigger label is
met (doc 12, Proven use).

- A load the host reported (`observed`) and one the adapter inferred from a read of the skill's `SKILL.md` both
  count, as the discovery probe counts them: some hosts, Codex among them, report no skill load of their own. The
  label names how many trigger runs rested on an inferred load only (`inferred_loads`).
- Only the with-skill arm of a trigger case is scored, as only it installs the skill. A trigger case passes when
  the skill loaded in at least half its scored runs if it should trigger, and in fewer than half if it should not.
- Trigger accuracy is that of the `test` split, the `train` split being for tuning a description. The trigger label
  is met when the skill has a test trigger case, each with at least `min_runs` scored runs, every planned trigger
  run was scored, and the accuracy reaches `trigger_accuracy` (10 · Skills); otherwise each gap is named.

Standard library only.
"""

from verdicts import EPSILON


def trigger_outcome(case, log):
    """(passed, inferred) of one with-skill trigger run of `case`: whether the skill loaded exactly when it should,
    and whether only an inferred load says it loaded."""
    sources = {entry.get("source") for entry in log if entry.get("kind") == "skill" and entry.get("name") == case.skill}
    return bool(sources) == bool(case.should_trigger), bool(sources) and "observed" not in sources


def passing(cases, scored):
    """(ids, passed) of the test trigger cases among `cases` (by id): their ids, and whether each case with a scored
    with-skill run passed, from `scored`, the outcomes of the scored runs by (case id, arm)."""
    triggers = [i for i, case in cases.items() if case.kind == "trigger" and case.split == "test"]
    passed = []
    for i in triggers:
        right = scored.get((i, "with_skill"), [])  # each run: did it do what the case says
        if right:  # the skill loaded in at least half the runs of a should-trigger case, in fewer of a should-not
            passed.append(2 * sum(right) >= len(right) if cases[i].should_trigger else 2 * sum(right) > len(right))
    return triggers, passed


def label(cases, scored, unsettled, inferred, thresholds):
    """The trigger label of one skill on one host: `cases` its cases by id, `scored` the outcomes of its scored runs by
    (case id, arm), `unsettled` the named trigger runs not scored, `inferred` how many scored ones rest on an inferred
    load only, and `thresholds` the label's (`verdicts.THRESHOLDS`)."""
    ids, passed = passing(cases, scored)
    runs = {f"{i}, with_skill": len(scored.get((i, "with_skill"), [])) for i in ids}
    accuracy = round(sum(passed) / len(passed), 4) if passed else None
    least, floor = thresholds["min_runs"], thresholds["trigger_accuracy"]
    gaps = ["test trigger cases: none"] * (not ids) + [
        f"{slot}: {count} scored run(s), {least} needed" for slot, count in sorted(runs.items()) if count < least]
    gaps += list(unsettled)
    if accuracy is not None and accuracy < floor - EPSILON:
        gaps.append(f"trigger accuracy {accuracy:.0%} below {floor:.0%}")
    return {"accuracy": accuracy, "threshold": floor, "cases": len(ids), "runs": runs, "inferred_loads": inferred,
            "met": not gaps, "gaps": gaps}
