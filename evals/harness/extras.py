"""The extra runs of a round (doc 12, Verdicts): more runs where a verdict is too close, and nowhere else.

One rule: a run is added only where a verdict asks for it (`wanted`). When a measure or floor of a label is `too
close`, each split case it reads gets 3 more runs in each arm it reads, and every label is decided again by the
same rule. The plan's `extra_runs` (0, 3 or 6, `runs.extra`) caps them per case and arm, so the gate makes at most
`extra_runs / 3` passes; 0 turns them off. Only the round's planned cases are extended, never the fault gate's
planted runs. An extra run goes through every step a planned run does: the run with its load proof
(`gates.run_one`, and the pinned-load stop, `gates.pinned_stop`), its checks (`gates.check_one`) and its grading
with every golden mixed in (`grades.grade`). Its number follows the case's planned and earlier extra runs.

The gate's outcome lists each pass's runs, checks, grades and the goldens it found untrusted; the label file reads
them with the planned runs (`labels.labels`) and names the extra runs of each case and arm.

Standard library only.
"""

import json

import grades
import labels
import prices
import runs

STEP = 3  # the runs one pass adds to a split case in each arm


def wanted(found, record, cases):
    """{(host, skill, case id, arm)} to extend, from the label file `found` (`labels.labels`): for each measure or
    floor that is `too close`, each case split in an arm it reads, in each arm it reads that the case runs in
    (`runs.arms`, from `cases` by (skill, case id))."""
    slots = set()
    for skill, hosts in found["skills"].items():
        for host, entry in hosts.items():
            for verdict in entry.get("verdicts", {}).values():
                if verdict["verdict"] != "too close":
                    continue
                for case_id in {i for listed in verdict["split"].values() for i in listed}:
                    allowed = runs.arms(record, cases[(skill, case_id)])
                    slots.update((host, skill, case_id, arm) for arm in verdict["split"] if arm in allowed)
    return slots


def extra_gate(r):
    """The extra runs gate of the round `r` (`gates.Round`), after the grade gate: {"passes": [each pass's
    {"runs", "checks", "grades", "goldens"}]}."""
    import gates  # the gates import this module for their list

    recorded = {g["gate"]: g for g in json.loads((r.folder / "attempts" / f"{r.attempt}.json").read_text())["gates"]}
    passes, done, price_file = [], {}, prices.load(r.repo)
    for number in range(1, runs.extra(r.record) // STEP + 1):
        so_far = {**recorded, "extra runs": {"passed": True, "outcome": {"passes": passes}}}
        slots = sorted(wanted(labels.labels(r.folder, r.attempt, r.record, r.cases, price_file, so_far), r.record,
                              r.cases))
        if not slots:
            break
        made = []
        for step in range(1, STEP + 1):  # each slot's next numbers, after its planned and earlier extra runs
            for slot in slots:
                made.append(gates.run_one(r, *slot, r.record["plan"]["runs"] + done.get(slot, 0) + step))
        for slot in slots:
            done[slot] = done.get(slot, 0) + STEP
        gates.pinned_stop(r, recorded["run"]["outcome"] + [m for found in passes for m in found["runs"]] + made)
        fresh = r.runs[-len(made):]
        checked = [gates.check_one(r, m) for m in fresh if m["status"] in ("kept", "made")]
        graded = grades.grade(r, fresh, r.folder / "grades" / r.attempt / f"extra-{number}")
        passes.append({"runs": made, "checks": checked, "grades": graded["runs"], "goldens": graded["goldens"]})
    return {"passes": passes}
