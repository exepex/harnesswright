"""The gates of a round (doc 11, Gates of a round): `round run` takes a planned round through its gates in order.

One rule: a round goes through `GATES` in order, each gate reads only the round's manifest and what the gates before
it found, and the first gate that fails stops the round with its reason. Each gate's outcome is written to the
round's attempt record as the gate ends, that of the gate that stopped the round too (`Stop`), so every gate a round
ran can be read back from the store. Every way an attempt ends, a caught signal too, writes why to the record before
the process exits (`endings`). Everything the round writes or reports passes one scrub (`Round.quiet`): the
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
  is kept, made, void, empty or not loaded does not stop the round; a canary, a failed audit or a broken run does.
  The gate's report gives why each slot is void, empty or not loaded, marks each pinned run (`runs.pinned`), and
  gives each without-skill run's shorter backstop matches. When half or more of the pinned tries are not loaded,
  counted as the pinned-load rate counts them (`runs.misses`), the gate stops the round as a harness fault: the pin
  is broken, not the skill (doc 12, Proven use).
- `check`: every expectation that has a check is decided on the bundle of each kept or made run
  (`checks.decide`), with the check library of the round's commit. The verdicts are written beside the bundle
  (`checks.json`, one per expectation, null for one with no check), and what no check decided is kept for the
  graders (`grading.questions`). A check that breaks stops the round.
- `grade`: what no check decided, answered by blind panels of graders with the goldens mixed in, each page's
  grading written to the attempt's own folder (`grades.grade_gate`).
- `extra runs`: while a measure or floor is `too close`, 3 more runs of each split case it reads, in each arm it
  reads, through the run, check and grade steps above, at most as many as the plan's `extra_runs` allows
  (`extras.extra_gate`). The fault gate's planted runs are never extended.
- `label`: the labels of 10 · Skills for each skill on each host, computed from the store alone and written to
  `labels/<attempt>.json` (`labels.label_gate`).

The store gate follows in a later step. Every gate runs again when a round is run again,
as each proves the kit and the hosts as they are now; only runs (`runs.run`) and their grades
(`grades.KEPT`) are kept.

Run from the repository root:

    python3 evals/harness/rounds.py run ROUND --store DIR [--host-path PATH ...] [--seed N]

Standard library only.
"""

import contextlib
import datetime
import json
import os
import random
import secrets
import shutil
import tempfile
from pathlib import Path

import checks
import endings
import extras
import faults
import grader
import grades
import grading
import kit
import labels
import lint
import probes
import rounds
import runs
import scrub
import skills
from cases import REPO, Case, CaseError


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
        self.attempt = None  # the name of the attempt (`run`)
        self.tokens, self.secrets = set(), set()  # of every containment the gates made (`keep`)
        self.modules = {name: rounds.adapter(name, adapters) for name in sorted(record["hosts"])}
        self.skills = skills.folders(self.repo)  # {name: folder}: where every gate reads each skill
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
    measuring, data = lint.eval_texts(r.repo)
    problems = []
    for host, module in r.modules.items():
        for (skill, case_id), case in r.cases.items():
            # Each arm that installs a version of the skill is linted with that version's text and the upstream
            # copy recorded in the same tree, the round's checkout or the previous version's commit. A skill with no
            # folder yet has only its without-skill arm, linted with no text of its own.
            for arm in [a for a in runs.arms(r.record, case) if a != runs.ARMS[0]] or runs.arms(r.record, case):
                with tempfile.TemporaryDirectory(prefix="hw-lint-") as out, contextlib.ExitStack() as stack:
                    try:
                        skill_dir, tree = None, r.repo
                        if arm == runs.PREVIOUS:
                            kept = r.record["previous"][skill]
                            skill_dir, read = stack.enter_context(rounds.previous(r.repo, skill, kept["commit"],
                                                                                  kept["sha256"]))
                            tree = skill_dir.parents[len(Path(read["path"]).parts) - 1]
                        upstream = lint.texts(tree / "evals" / "skills" / skill / "upstream")
                        found = lint.lint_case(case, module, out, r.skills, skill_dir, upstream, measuring,
                                               r.repo, data)
                    except (CaseError, rounds.RoundError) as error:
                        found = [str(error)]
                problems += [f"{host}, {skill}/{case_id}, {arm}: {problem}" if arm == runs.PREVIOUS
                             else f"{host}, {skill}/{case_id}: {problem}" for problem in found]
    if problems:
        raise Stop("; ".join(problems), {"problems": problems})
    return {"cases": len(r.cases), "hosts": len(r.modules)}


def installed(r):
    """{"lines", "bytes"} of the longest `SKILL.md` the round installs (`probes.length`): each skill its manifest
    records and each previous version, the length the pinned-load probe's skill must reach."""
    with contextlib.ExitStack() as stack:
        paths = [r.skills[name] / "SKILL.md" for name in sorted(r.record["skills"])]
        for name, kept in sorted(r.record.get("previous", {}).items()):
            folder, _ = stack.enter_context(rounds.previous(r.repo, name, kept["commit"], kept["sha256"]))
            paths.append(folder / "SKILL.md")
        return probes.length(paths)


def probe_gate(r):
    tools = sorted({tool for case in r.cases.values() for tool in case.tools})
    longest = installed(r)
    not_run, drift = {}, {}
    for host, module in r.modules.items():
        made = []
        with tempfile.TemporaryDirectory(prefix="hw-p-") as scratch:  # the probes' homes, kept until scrubbed
            try:
                found = probes.probe_host(module, scratch, tools=tools, model=r.model(host), timeout=r.timeout,
                                          made=made, length=longest, **r.containment)
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
    # Every fault needs a skill's files, so faults are planted on a case of a skill the repository holds: the plan's
    # `fault_case`, or else one of the round's own that runs in both arms, chosen by the seed.
    chosen = r.record.get("fault_case")
    held = sorted(k for k, case in r.cases.items() if set(runs.ARMS) <= set(runs.arms(r.record, case)))
    for host, passed in r.hosts.items():
        if chosen:
            case = Case(r.repo / "evals" / "skills" / chosen["skill"] / "cases" / chosen["case"], chosen["skill"])
            if case.sha256 != chosen["sha256"]:
                raise Stop(f"fault_case {chosen['skill']}/{chosen['case']} changed since the round was planned", {})
        else:
            case = r.cases[rng.choice(held)]
        kept = r.folder / "faults" / f"{r.seed}-{secrets.token_hex(4)}" / host
        # Plants and runs under a short temporary folder, as every jail's socket path must stay short; each fault's
        # bundles are copied to the store for the judges.
        with tempfile.TemporaryDirectory(prefix="hw-f-") as scratch:
            setup = faults.Setup(r.modules[host], case, r.skills, scratch, passed["drift"],
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


def order(record, hosts, cases, extra=None, steps=None):
    """Every planned run of `hosts`, as (host, skill, case id, arm, number): for each number, each case in turn,
    its arms (`runs.arms`, from `cases` by (skill, case id)) one after the other, the arm that goes first turning
    from case to case and number to number. With `extra` ({(host, skill, case id, arm): the runs it has}), the
    `steps` next runs of each of those slots only, in the same turn (`extras.extra_gate`): one order for both."""
    planned = [(skill, i) for skill in sorted(record["cases"]) for i in sorted(record["cases"][skill])]
    for step in range(1, (steps or record["plan"]["runs"]) + 1):
        for index, (skill, case_id) in enumerate(planned):
            arms = runs.arms(record, cases[(skill, case_id)])
            turn = (step + index + 1) % len(arms)  # the first arm moves on by one each case and number
            for arm in arms[turn:] + arms[:turn]:
                for host in sorted(hosts):
                    if extra is None:
                        yield host, skill, case_id, arm, step
                    elif (host, skill, case_id, arm) in extra:
                        yield host, skill, case_id, arm, extra[(host, skill, case_id, arm)] + step


def run_gate(r):
    made = [run_one(r, *slot) for slot in order(r.record, r.hosts, r.cases)]
    pinned_stop(r, made)
    return made


def run_one(r, host, skill, case_id, arm, number):
    """One run of the round `r`, as the run gate reports it, kept in `r.runs` with its bundle."""
    result = runs.run(r.record, r.store, r.cases[(skill, case_id)], arm, host, number, r.modules[host],
                      r.hosts[host]["drift"], r.version(host), timeout=r.timeout, repo=r.repo, **r.containment)
    made = {"host": host, "skill": skill, "case": case_id, "arm": arm, "number": number, "key": result["key"],
            "status": result["status"]}
    if result.get("reason"):  # why a slot is void, empty or not loaded, such as a backstop hit, for a judge
        made["reason"] = result["reason"]
    if runs.pinned(r.record, r.cases[(skill, case_id)], arm):
        made["pinned"] = True
    short = Path(result["bundle"]).parent / runs.SHORT if result.get("bundle") else None
    if short and short.is_file():  # the backstop's shorter matches, listed and never a void
        made["backstop"] = json.loads(short.read_text())["short"]
    r.runs.append({**made, "bundle": result.get("bundle")})
    return made


def pinned_stop(r, made):
    """Stop the round as a harness fault when half or more of the pinned tries of `made` are not loaded."""
    pinned = [m for m in made if m.get("pinned")]  # counted by try, as the pinned-load rate counts them
    missed = sum(runs.misses(r.folder / "runs" / m["key"]) for m in pinned)
    tries = missed + sum(m["status"] in ("kept", "made") for m in pinned)
    if missed and 2 * missed >= tries:
        raise Stop(f"harness fault: {missed} of {tries} pinned tries are not loaded, so the pin is broken, "
                   "not the skill", made)


def check_gate(r):
    return [check_one(r, made) for made in r.runs if made["status"] in ("kept", "made")]


def check_one(r, made):
    """The check verdicts of one kept or made run, written beside its bundle; what no check decided goes to
    `r.asked` for the graders."""
    library = checks.library(r.repo / "evals" / "checks")
    expectations = r.cases[(made["skill"], made["case"])].expectations
    bundle = checks.Bundle.load(made["bundle"])
    verdicts = [checks.decide(e["check"]["name"], bundle, e["check"].get("args", {}), library)
                if "check" in e else None for e in expectations]
    r.asked[made["key"]] = grading.questions(expectations, verdicts)
    r.write(Path(made["bundle"]).parent / "checks.json", {"verdicts": verdicts})
    outcomes = [v["outcome"] for v in verdicts if v]
    return {"key": made["key"], **{o: outcomes.count(o) for o in checks.OUTCOMES},
            "asked": [question["id"] for question in r.asked[made["key"]]]}


GATES = (("kit check", kit_check), ("lint", lint_gate), ("probe", probe_gate), ("faults", faults_gate),
         ("run", run_gate), ("check", check_gate), ("grade", grades.grade_gate), ("extra runs", extras.extra_gate),
         ("label", labels.label_gate))


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
    path = endings.claim(r.folder / "attempts")  # a new name for every attempt, in the order they start
    r.attempt = path.stem  # names what this attempt alone writes, such as its grades
    gate = None
    with endings.signals(path, attempt, lambda: gate, r.quiet):  # every end writes why (`endings.end`)
        try:
            for gate, step in gates:
                try:
                    outcome = step(r)
                except Exception as error:  # any error stops the round at this gate, with its reason
                    reason = r.quiet(str(error) if isinstance(error, Stop) else f"{type(error).__name__}: {error}")
                    stopped = {"gate": gate, "passed": False, "reason": reason}
                    reason = r.quiet(str(error))
                    attempt["gates"].append({**stopped, **({"outcome": error.outcome} if isinstance(error, Stop)
                                                           else {})})
                    endings.end(path, attempt, f"stopped at the {gate} gate: {stopped['reason']}", r.quiet)
                    raise rounds.RoundError(f"round {name} stopped at the {gate} gate: {reason}") from error
                attempt["gates"].append({"gate": gate, "passed": True, "outcome": outcome})
                _write(path, attempt, r.quiet)
            endings.end(path, attempt, endings.PASSED, r.quiet)
        except BaseException as error:  # an exit or an interrupt not caught as a signal: why, before it goes on
            said = f": {error}" if str(error) else ""
            endings.end(path, attempt, f"{type(error).__name__} during the {gate} gate{said}", r.quiet)
            if isinstance(error, endings.Ended):
                raise rounds.RoundError(f"round {name} {error}") from None
            raise
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
