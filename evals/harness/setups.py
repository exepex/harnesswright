"""The setup of a round (doc 12, One setup): one fingerprint of everything that measures a skill, except the skill.

One rule: two results of a skill compare only when their setups have the same fingerprint, and the fingerprint is
made in one place (`setup`) from the round's manifest and the code that turns runs into labels. Its parts, each
named so a change can be named (`changed`):

- `kit`: the measuring kit's hash; `cases`: the skill's cases, each hash holding its world; `situations`: the
  situations the skill's cases are held to;
- `siblings`: the other skills this skill's own cases install (each case's `siblings`), as the manifest records
  them. Another skill the round plans beside it installs nothing in its worlds, so it is no part. The fault gate's
  skill (`fault_case`) is a part only when the fault is planted on one of this skill's own cases, and then it is
  this skill, which the setup leaves out;
- `adapters`, and `hosts`: each host's version and the model it runs; `graders`: the hosts that passed their probes,
  which grade the round's pages (`grades.panel`); `tools`: for each of those hosts, the tools and drift probe's
  record (`probes.drift`, `<round>/drift/<host>.json`) of each tool this skill's own cases declare, as a check runs
  them. The files a host writes for itself (`own files`) are left out: they may differ by name only;
- `runs` per case, arm and host, and `pinned`, whether task runs pin the skill's load;
- `runner`: the code that makes a run (`runs.runner`), and `label rule`: the code that turns a run's bundle into
  its label (`LABEL_RULE`).

It leaves out the skill's own hash and its previous version's: a result records those apart (`results.py`), so a
changed skill on one setup is still comparable.

Standard library only.
"""

import hashlib
import json
from pathlib import Path

import manifest
import runs

HARNESS = Path(__file__).resolve().parent
LABEL_RULE = ("checks.py", "goldens.py", "grader.py", "grades.py", "grading.py", "labels.py", "measures.py",
              "setups.py", "triggers.py", "verdicts.py", "view.py")


def setup(record, skill, cases, drift, folder=HARNESS):
    """{"parts", "fingerprint"} of the setup that measured `skill` in the round whose manifest is `record`: `cases`
    are the skill's own cases by id, `drift` the tools and drift record of each host that passed its probes (the
    hosts that grade), and `folder` holds the harness code."""
    siblings = sorted({name for case in cases.values() for name in case.siblings or ()} - {skill})
    tools = sorted({tool for case in cases.values() for tool in case.tools or ()})
    parts = {"kit": record["kit"], "cases": record["cases"][skill],
             "situations": record.get("situations", {}).get(skill),
             "siblings": {name: record["skills"][name] for name in siblings},
             "tools": {host: {tool: found["tools"].get(tool) for tool in tools} for host, found in drift.items()},
             "adapters": record["adapters"],
             "hosts": {name: {"version": host["version"], "model": host["model"]}
                       for name, host in record["hosts"].items()},
             "graders": sorted(drift), "runs": record["plan"]["runs"], "pinned": record.get("pinned") is True,
             "runner": runs.runner(folder),
             "label rule": manifest.digest({name: manifest.entry(Path(folder) / name) for name in LABEL_RULE})}
    return {"parts": parts, "fingerprint": hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()}


def changed(before, after):
    """The names of the parts in which setup `after` differs from setup `before`, in order."""
    return sorted(name for name in set(before["parts"]) | set(after["parts"])
                  if before["parts"].get(name) != after["parts"].get(name))
