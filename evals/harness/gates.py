"""The gates of a round (doc 11, Gates of a round): `round run` takes a planned round through its gates in order.

One rule: a round goes through `GATES` in order, each gate reads only the round's manifest and what the gates before
it found, and the first gate that fails stops the round with its reason. Each gate's outcome is written to the
round's attempt record as the gate ends, so every gate a round passed, and the one that stopped it, can be read
back from the store.

- `kit check`: the measuring kit matches the judges' approval (`kit.check`), and it is the kit the manifest hashed.
- `lint`: every planned case passes world lint (`lint.lint_case`) on every host.
- `probe`: each host passes every probe and the tools and drift probe (`probes.probe_host`). A host that fails is
  `not run` for the round, with its reasons; the round stops only when no host passed.
- `faults`: every fault of the catalogue (`faults.load`) is planted on each host that passed its probes, at a place
  the round's seed chooses, and every one must be caught.
- `run`: every planned run of each host that passed (`runs.run`), cases and arms interleaved (`order`). A run that
  is kept, made, void or empty does not stop the round; a canary, a failed audit or a broken run does.

The check, grade, label and store gates follow in later steps. Every gate runs again when a round is run again,
as each proves the kit and the hosts as they are now; only runs are kept (`runs.run`).

Run from the repository root:

    python3 evals/harness/rounds.py run ROUND --store DIR [--host-path PATH ...] [--seed N]

Standard library only.
"""

import datetime
import json
import os
import random
import secrets
import tempfile
from pathlib import Path

import faults
import kit
import lint
import probes
import rounds
import runs
from cases import REPO, Case, CaseError
from runs import ARMS


class Round:
    """A planned round as its gates see it: the manifest `record`, its adapters and cases, the hosts that passed
    their probes (`hosts`: name: {"drift", "version"}), and the options of every host run."""

    def __init__(self, record, store, repo=REPO, adapters=rounds.ADAPTERS, seed=None, timeout=runs.TIMEOUT,
                 **containment):
        self.record, self.store, self.repo, self.timeout = record, store, Path(repo), timeout
        self.seed = secrets.randbelow(2 ** 32) if seed is None else seed
        self.containment, self.hosts = containment, {}
        self.modules = {name: rounds.adapter(name, adapters) for name in sorted(record["hosts"])}
        root = self.repo / "evals" / "skills"
        self.cases = {(skill, i): Case(root / skill / "cases" / i, skill)
                      for skill in sorted(record["cases"]) for i in sorted(record["cases"][skill])}

    def model(self, host):
        return self.record["hosts"][host]["model"]


def kit_check(r):
    approved = kit.check(r.store, r.repo)
    if approved != r.record["kit"]:
        raise rounds.RoundError(f"the approved kit {approved} is not the kit the manifest hashed {r.record['kit']}")
    return {"approved": approved}


def lint_gate(r):
    upstream = {skill: lint.texts(r.repo / "evals" / "skills" / skill / "upstream") for skill in r.record["cases"]}
    measuring, data = lint.eval_texts(r.repo)
    problems = []
    for host, module in r.modules.items():
        for (skill, case_id), case in r.cases.items():
            with tempfile.TemporaryDirectory(prefix="hw-lint-") as out:
                try:
                    found = lint.lint_case(case, module, out, r.repo / "skills", None, upstream[skill], measuring,
                                           r.repo, data)
                except CaseError as error:
                    found = [str(error)]
            problems += [f"{host}, {skill}/{case_id}: {problem}" for problem in found]
    if problems:
        raise rounds.RoundError("; ".join(problems))
    return {"cases": len(r.cases), "hosts": len(r.modules)}


def probe_gate(r):
    tools = sorted({tool for case in r.cases.values() for tool in case.tools})
    not_run = {}
    for host, module in r.modules.items():
        found = probes.probe_host(module, tools=tools, model=r.model(host), timeout=r.timeout, **r.containment)
        if found["not run"]:
            not_run[host] = found["not run"]
        else:
            r.hosts[host] = {"drift": found["drift"], "version": rounds.host_version(module, **r.containment)}
    if not r.hosts:
        raise rounds.RoundError(f"no host passed its probes: {json.dumps(not_run, sort_keys=True)}")
    return {"passed": sorted(r.hosts), "not run": not_run}


def faults_gate(r):
    entries, rng = faults.load(r.repo / "evals" / "faults" / "harness.json"), random.Random(r.seed)
    found, missed = {}, []
    for host, passed in r.hosts.items():
        case = r.cases[rng.choice(sorted(r.cases))]
        folder = kit.store_folder(r.store, r.repo) / r.record["round"] / "faults" / f"{r.seed}" / host
        setup = faults.Setup(r.modules[host], case, r.repo / "skills", folder, passed["drift"],
                             model=r.model(host), host_version=passed["version"]["version"], timeout=r.timeout,
                             repo=r.repo, **r.containment)
        found[host] = []
        for entry in entries:
            result = faults.run(entry, setup, f"{r.seed}:{host}:{entry['id']}")
            found[host].append({k: result[k] for k in ("id", "place", "caught", "reason", "seen")})
            if not result["caught"]:
                missed.append(f"{host}, {entry['id']} at {result['place']}: {result['reason']}")
    if missed:
        raise rounds.RoundError("faults missed: " + "; ".join(missed))
    return found


def order(record, hosts):
    """Every planned run of `hosts`, as (host, skill, case id, arm, number): for each number, each case in turn,
    its two arms one after the other, the arm that goes first alternating from case to case and number to number."""
    planned = [(skill, i) for skill in sorted(record["cases"]) for i in sorted(record["cases"][skill])]
    for number in range(1, record["plan"]["runs"] + 1):
        for index, (skill, case_id) in enumerate(planned):
            for arm in (ARMS if (number + index) % 2 else ARMS[::-1]):
                for host in sorted(hosts):
                    yield host, skill, case_id, arm, number


def run_gate(r):
    made = []
    for host, skill, case_id, arm, number in order(r.record, r.hosts):
        passed = r.hosts[host]
        result = runs.run(r.record, r.store, r.cases[(skill, case_id)], arm, host, number, r.modules[host],
                          passed["drift"], passed["version"], timeout=r.timeout, repo=r.repo, **r.containment)
        made.append({"host": host, "skill": skill, "case": case_id, "arm": arm, "number": number,
                     "key": result["key"], "status": result["status"]})
    return made


GATES = (("kit check", kit_check), ("lint", lint_gate), ("probe", probe_gate), ("faults", faults_gate),
         ("run", run_gate))


def read(store, name, repo=REPO):
    """The manifest of round `name` in `store`, as `rounds.write` wrote it."""
    if not rounds.is_name(name):
        raise rounds.RoundError(f"{name!r}: not a round's name")
    try:
        path = kit.store_folder(Path(store) / name / rounds.MANIFEST, repo)
        if not path.is_file():
            raise rounds.RoundError(f"{path}: round {name} has no manifest; plan it first")
        return json.loads(path.read_text())
    except (kit.KitError, OSError, ValueError) as error:
        raise rounds.RoundError(f"round {name}: its manifest cannot be read: {error}") from None


def run(store, name, repo=REPO, adapters=rounds.ADAPTERS, gates=GATES, **options):
    """Take round `name` of `store` through `gates` in order, from the repository `repo` at the round's commit.
    Return the attempt record; raise RoundError, naming the gate, at the first gate that fails."""
    record = read(store, name, repo)
    if rounds.commit(repo) != record["commit"]:
        raise rounds.RoundError(f"{repo} is not at round {name}'s commit {record['commit']}")
    r = Round(record, store, repo, adapters, **options)
    started = datetime.datetime.now(datetime.timezone.utc)
    attempt = {"round": name, "seed": r.seed, "started": started.isoformat(timespec="seconds"), "gates": []}
    folder = kit.store_folder(store, repo) / name / "attempts"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{started.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}.json"
    for gate, step in gates:
        try:
            outcome = step(r)
        except Exception as error:  # any error stops the round at this gate, with its reason
            attempt["gates"].append({"gate": gate, "passed": False, "reason": f"{type(error).__name__}: {error}"})
            _write(path, attempt)
            raise rounds.RoundError(f"round {name} stopped at the {gate} gate: {error}") from error
        attempt["gates"].append({"gate": gate, "passed": True, "outcome": outcome})
        _write(path, attempt)
    return attempt


def _write(path, attempt):
    fresh = path.with_name(f".{path.name}")
    fresh.write_text(json.dumps(attempt, indent=1, sort_keys=True) + "\n")
    os.replace(fresh, path)
