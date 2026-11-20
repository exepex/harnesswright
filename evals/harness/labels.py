"""The label gate of a round (doc 11, Rounds, results and labels): the labels of 10 · Skills, from the store alone.

One rule: a label is computed by one function (`labels`) from what the round stored: the attempt record, and for
each kept or made run its bundle, its check verdicts and its trusted grades. A rerun on the same store gives the
same label. And a label rests only on settled results: every planned run that is not scored, whatever the reason,
is named, and so is a reference result that is not settled, and either keeps the label at most `inconclusive`.
This module is the one entry point callers use (`labels`, `label_gate`). It scores each stored run and writes the
label file; a task run's outcome, the measures and the label itself are `verdicts.py`'s, and a trigger run's
outcome is `triggers.py`'s.

- A task run is a false done when the graders' trusted answer to the done question is `yes` and the run fails.
  Each label gives, per arm, `false_done`: the false dones of the runs where both are decided, and how many are
  not decided.
- A planned run is not scored when it is void, empty or not loaded (a pinned run with no proven load, doc 12), or
  its outcome is not decided. Each is named (`unsettled`), and so is each case and arm whose pinned runs never
  loaded. The pinned-load rate per arm comes with the other measures (`measures.measures`).
- A host other than the reference host is held to the reference host's measures only when those are settled;
  otherwise its label names why.
- The label file of an attempt is written to `<store>/<round>/labels/<attempt>.json`, through the round's scrub. It
  records each skill's setup (`setups.setup`), the one fingerprint two results must share to be compared.

Standard library only.
"""

import json

import evidence
import grades
import measures
import prices
import setups
import triggers
import verdicts
from cases import SKILL_ONLY

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
    found = {"round": record["round"], "attempt": attempt, "commit": record["commit"],
             "thresholds": verdicts.THRESHOLDS, "reference": grades.REFERENCE, "prices": price_file["date"],
             "skills": {},
             "setups": {skill: setups.setup(record, skill, passed) for skill in sorted(record["cases"])}}
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
            if verdicts.missing(measured[grades.REFERENCE]) or verdicts.doubts(
                    measured[grades.REFERENCE], doubted[grades.REFERENCE],
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
                             **verdicts.decide({**measured[host], **rest.get((host, skill), {})}, doubted[host],
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
