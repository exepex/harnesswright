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
- `runs` per case, arm and host, `extra runs`, the cap on a split case's extra runs (`runs.extra`), which changes
  what a verdict may conclude, and `pinned`, whether task runs pin the skill's load. A round with no extra runs has
  no `extra runs` part, so its fingerprint is the one it had before the cap existed;
- `runner`: the code that makes a run (`runs.runner`), and `label rule`: the code that turns a run's bundle into
  its label: the files of the kit's `label rule` part (`evals/kit.json`, `kit.parts`), the one list of them.

It leaves out the skill's own hash and its previous version's: a result records those apart (`results.py`), so a
changed skill on one setup is still comparable.

Standard library only.
"""

import hashlib
import json
from pathlib import Path

import kit
import manifest
import runs

HARNESS = Path(__file__).resolve().parent


def setup(record, skill, cases, drift, folder=HARNESS):
    """{"parts", "fingerprint"} of the setup that measured `skill` in the round whose manifest is `record`: `cases`
    are the skill's own cases by id, `drift` the tools and drift record of each host that passed its probes (the
    hosts that grade), and `folder` holds the harness code, in the repository whose kit list names the label rule:
    each of its files is read at its path in that repository, such as the resolver's names the view reads."""
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
             **({"extra runs": runs.extra(record)} if runs.extra(record) else {}),  # none: as before the cap was
             "runner": runs.runner(folder),
             "label rule": manifest.digest({path: manifest.entry(Path(folder).parents[1] / path)
                                            for path in kit.parts(Path(folder).parents[1])["label rule"]})}
    return {"parts": parts, "fingerprint": hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()}


def changed(before, after):
    """The names of the parts in which setup `after` differs from setup `before`, in order."""
    return sorted(name for name in set(before["parts"]) | set(after["parts"])
                  if before["parts"].get(name) != after["parts"].get(name))
