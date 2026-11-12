"""The gates of a round (doc 11, Gates of a round): `round run` takes a planned round through its gates in order.

One rule: a round goes through `GATES` in order, each gate reads only the round's manifest and what the gates before
it found, and the first gate that fails stops the round with its reason. Each gate's outcome is written to the
round's attempt record as the gate ends, that of the gate that stopped the round too (`Stop`), so every gate a round
ran can be read back from the store. Everything the round writes or reports passes one scrub (`Round.quiet`): the
canaries and credentials of every containment its gates made, taken while its home is still there (`Round.keep`).

- `kit check`: the measuring kit matches the judges' approval (`kit.check`), and it is the kit the manifest hashed.
- `lint`: every planned case passes world lint (`lint.lint_case`) on every host.
- `probe`: each host passes every probe and the tools and drift probe (`probes.probe_host`). A host that fails is
  `not run` for the round, with its reasons; the round stops only when no host passed. The drift record of the
  first attempt a host passed is the round's, kept in the store (`drift/<host>.json`) and used by every later
  attempt, as a host's own files can differ by name from one empty run to the next and the record is in each run's
  key. Tools that are not the round's stop it.
- `faults`: every fault of the catalogue (`faults.load`) is planted on each host that passed its probes, at a place
  the round's seed chooses, and every one must be caught. The bundles of its runs are copied to the store.
- `run`: every planned run of each host that passed (`runs.run`), cases and arms interleaved (`order`), each with
  the host's version measured just before it, so a host that changed during the round voids its runs. A run that
  is kept, made, void or empty does not stop the round; a canary, a failed audit or a broken run does.
- `check`: every expectation that has a check is decided on the bundle of each kept or made run
  (`checks.decide`), with the check library of the round's commit. The verdicts are written beside the bundle
  (`checks.json`, one per expectation, null for one with no check), and what no check decided is kept for the
  graders (`grading.questions`). A check that breaks stops the round.
- `grade`: what no check decided, answered by blind panels of graders with the goldens mixed in, each run's
  answers written beside its bundle (`grades.grade_gate`).

The label and store gates follow in later steps. Every gate runs again when a round is run again,
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
import shutil
import tempfile
from pathlib import Path

import checks
import faults
import grader
import grades
import grading
import kit
import lint
import probes
import rounds
import runs
import scrub
from cases import REPO, Case, CaseError
from runs import ARMS


class Stop(rounds.RoundError):
    """A gate that failed, with its reason and what it found, which the attempt record keeps."""

    def __init__(self, reason, outcome):
        super().__init__(reason)
        self.outcome = outcome


class Round:
    """A planned round as its gates see it: the manifest `record`, its adapters and cases, the hosts that passed
    their probes (`hosts`: name: {"drift"}), the runs the run gate gave (`runs`), what no check decided of each
    (`asked`: run key: questions), and the options of every host run."""

    def __init__(self, record, store, repo=REPO, adapters=rounds.ADAPTERS, seed=None, timeout=runs.TIMEOUT,
                 version=rounds.host_version, grade=grader.grade, **containment):
        self.record, self.store, self.repo, self.timeout = record, store, Path(repo), timeout
        self.folder = kit.store_folder(store, repo) / record["round"]
        self.seed = secrets.randbelow(2 ** 32) if seed is None else seed
        self.containment, self.hosts, self.runs, self.asked = containment, {}, [], {}
        self.tokens, self.secrets = set(), set()  # of every containment the gates made (`keep`)
        self.modules = {name: rounds.adapter(name, adapters) for name in sorted(record["hosts"])}
        root = self.repo / "evals" / "skills"
        self.cases = {(skill, i): Case(root / skill / "cases" / i, skill)
                      for skill in sorted(record["cases"]) for i in sorted(record["cases"][skill])}

        self.measure = version  # a host's version as its jail finds it now (`rounds.host_version`)
        self.grade = grade  # one grader run of one page (`grader.grade`)

    def model(self, host):
        return self.record["hosts"][host]["model"]

    def keep(self, made):
        """Remember the canaries and credentials of the containments `made`, while their homes are still there, so
        a credential a host refreshed in its home is known after the home is gone."""
        for contained in made:
            self.tokens.update(contained.tokens)
            self.secrets.update(scrub.credentials(contained))

    def quiet(self, text):
        """`text` with every canary and credential the round has kept (`keep`) replaced."""
        return scrub.Scrub(self.tokens, self.secrets).quiet(text)

    def write(self, path, data):
        """Write `data` to the round's file at `path`, scrubbed (`quiet`)."""
        _write(path, data, self.quiet)

    def version(self, host):
        return self.measure(self.modules[host], **self.containment)


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
        raise Stop("; ".join(problems), {"problems": problems})
    return {"cases": len(r.cases), "hosts": len(r.modules)}


def probe_gate(r):
    tools = sorted({tool for case in r.cases.values() for tool in case.tools})
    not_run, drift = {}, {}
    for host, module in r.modules.items():
        made = []
        with tempfile.TemporaryDirectory(prefix="hw-p-") as scratch:  # the probes' homes, kept until scrubbed
            try:
                found = probes.probe_host(module, scratch, tools=tools, model=r.model(host), timeout=r.timeout,
                                          made=made, **r.containment)
            finally:  # a probe that raised made containments too, whose words its error may carry
                r.keep(made)
        found = json.loads(r.quiet(json.dumps(found)))  # its reasons and drift record, as they may be kept
        if found["not run"]:
            not_run[host] = found["not run"]
        else:
            r.hosts[host] = {"drift": _pin(r.folder / "drift" / f"{host}.json", found["drift"])}
            drift[host] = "the round's" if r.hosts[host]["drift"] == found["drift"] else found["drift"]
            if r.hosts[host]["drift"]["tools"] != found["drift"]["tools"]:  # only own files may differ by name
                raise Stop(f"{host}: its tools are not the round's", {"not run": not_run, "drift": drift})
    if not r.hosts:
        raise Stop("no host passed its probes", {"not run": not_run})
    return {"passed": sorted(r.hosts), "not run": not_run, "drift": drift}


def faults_gate(r):
    entries, rng = faults.load(r.repo / "evals" / "faults" / "harness.json"), random.Random(r.seed)
    found, missed = {}, []
    for host, passed in r.hosts.items():
        case = r.cases[rng.choice(sorted(r.cases))]
        kept = r.folder / "faults" / f"{r.seed}-{secrets.token_hex(4)}" / host
        # Plants and runs under a short temporary folder, as every jail's socket path must stay short; each fault's
        # bundles are copied to the store for the judges.
        with tempfile.TemporaryDirectory(prefix="hw-f-") as scratch:
            setup = faults.Setup(r.modules[host], case, r.repo / "skills", scratch, passed["drift"],
                                 model=r.model(host), host_version=r.version(host)["version"], timeout=r.timeout,
                                 repo=r.repo, **r.containment)
            found[host] = []
            for entry in entries:
                result = faults.run(entry, setup, f"{r.seed}:{host}:{entry['id']}")
                bundles = []
                for number, bundle in enumerate(result["bundles"]):
                    bundles.append(kept / entry["id"] / str(number))
                    shutil.copytree(bundle, bundles[-1], symlinks=True)
                outcome = {k: result[k] for k in ("id", "place", "caught", "reason", "seen")}  # scrubbed by `run`
                found[host].append({**outcome, "bundles": [str(b) for b in bundles]})
                if not result["caught"]:
                    missed.append(f"{host}, {entry['id']} at {result['place']}: {result['reason']}")
    if missed:
        raise Stop("faults missed: " + "; ".join(missed), found)
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
        result = runs.run(r.record, r.store, r.cases[(skill, case_id)], arm, host, number, r.modules[host],
                          r.hosts[host]["drift"], r.version(host), timeout=r.timeout, repo=r.repo, **r.containment)
        made.append({"host": host, "skill": skill, "case": case_id, "arm": arm, "number": number,
                     "key": result["key"], "status": result["status"]})
        r.runs.append({**made[-1], "bundle": result.get("bundle")})
    return made


def check_gate(r):
    library, found = checks.library(r.repo / "evals" / "checks"), []
    for made in r.runs:
        if made["status"] not in ("kept", "made"):
            continue
        expectations = r.cases[(made["skill"], made["case"])].expectations
        bundle = checks.Bundle.load(made["bundle"])
        verdicts = [checks.decide(e["check"]["name"], bundle, e["check"].get("args", {}), library)
                    if "check" in e else None for e in expectations]
        r.asked[made["key"]] = grading.questions(expectations, verdicts)
        r.write(Path(made["bundle"]).parent / "checks.json", {"verdicts": verdicts})
        outcomes = [v["outcome"] for v in verdicts if v]
        found.append({"key": made["key"], **{o: outcomes.count(o) for o in checks.OUTCOMES},
                      "asked": [question["id"] for question in r.asked[made["key"]]]})
    return found


GATES = (("kit check", kit_check), ("lint", lint_gate), ("probe", probe_gate), ("faults", faults_gate),
         ("run", run_gate), ("check", check_gate), ("grade", grades.grade_gate))


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
    folder = r.folder / "attempts"
    folder.mkdir(parents=True, exist_ok=True)
    handle, path = tempfile.mkstemp(prefix=f"{started.strftime('%Y%m%dT%H%M%S')}-", suffix=".json", dir=folder)
    os.close(handle)  # a new name for every attempt, never another attempt's
    path = Path(path)
    for gate, step in gates:
        try:
            outcome = step(r)
        except Exception as error:  # any error stops the round at this gate, with its reason
            reason = r.quiet(str(error) if isinstance(error, Stop) else f"{type(error).__name__}: {error}")
            stopped = {"gate": gate, "passed": False, "reason": reason}
            reason = r.quiet(str(error))
            attempt["gates"].append({**stopped, **({"outcome": error.outcome} if isinstance(error, Stop) else {})})
            _write(path, attempt, r.quiet)
            raise rounds.RoundError(f"round {name} stopped at the {gate} gate: {reason}") from error
        attempt["gates"].append({"gate": gate, "passed": True, "outcome": outcome})
        _write(path, attempt, r.quiet)
    return json.loads(r.quiet(json.dumps(attempt)))


def _pin(path, record):
    """The record at `path`, written there first when there is none: written once, never replaced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = path.with_name(f".{path.name}.{os.getpid()}")
    fresh.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
    try:
        os.link(fresh, path)  # makes the record only where no entry has its name
    except FileExistsError:
        pass
    finally:
        fresh.unlink()
    if path.is_symlink() or not path.is_file():
        raise rounds.RoundError(f"{path}: not a regular file")
    return json.loads(path.read_text())


def _write(path, data, quiet):
    """Write `data` to `path` as JSON, whole: written beside it, then moved over it."""
    fresh = path.with_name(f".{path.name}")
    fresh.write_text(quiet(json.dumps(data, indent=1, sort_keys=True)) + "\n")
    os.replace(fresh, path)
