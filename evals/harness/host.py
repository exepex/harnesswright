"""Hosts: the one contract between the harness and a host's adapter (doc 11, Containment and Evidence).

One rule: the harness knows a host only through `CONTRACT`, and accepts from it only what the allow lists below
describe. `check_adapter` checks an adapter once, when it is loaded. `run` is the one place a host runs: in the
run's jail, after its audit and inside its gate, with the command the adapter builds. It returns the host's action
log and what the host exposed, each checked against one allow list: every entry has exactly the fields of its kind,
every exposed skill is one the case declares, and every exposed tool is one of the adapter's TOOLS, each of a kind
on the power table (`powers.TOOLS`). Anything else raises HostError, and the round stops. Each world file a
command names becomes an inferred read (`named`), whatever the adapter reported.

Standard library only.
"""

import fnmatch
import hashlib
import os
import re
import subprocess
import time

import manifest
import powers
import scrub

# The names every harness adapter defines, with what each must be.
CONTRACT = {
    "NAME": str,
    "CLI": str,  # the host's program; its install is what the jail mounts
    "MODEL_HOSTS": tuple,  # the gate's allow list (doc 11, The gate)
    "ENV_KEYS": tuple,
    "CREDENTIAL_FILES": tuple,
    "RUN_ENV": dict,  # fixed variables the adapter sets for every run, never taken from the operator (contain.py)
    "TOOLS": dict,  # each tool the host may expose, by the host's name, with its kind in powers.TOOLS
    "skill_dir": callable,  # (world, name): where the host discovers a skill in the world
    # (home, world): the files outside the world where the host reads memory or the user's own instructions, for a
    # home and a world; the memory probe plants a decoy in each, and none may reach a run (probes.py)
    "memory_files": callable,
    "environment": callable,  # (env): the run's environment, given the one the harness built (contain.py)
    # (mode, world, model): the command for one run, with the prompt on stdin. The host's own sandbox is off (the
    # jail enforces the table), its bundled skills are off where it allows, and it exposes only its TOOLS.
    "jail_command": callable,
    # (stdout, home): the host-neutral action log, a list of ENTRIES, where a write that failed may also be
    # {"kind": "failed", "source", "action", "path", "reason"} and the harness decides what it was (`settle`)
    "action_log": callable,
    # (stdout, home): {"skills": [names], "tools": [host tool names]} as the host reported them, or None when it
    # did not report them, which only a failed run may do
    "exposure": callable,
    "run_failure": callable,  # (stdout, returncode, timed_out): why the host failed, such as a crash, or None
    # (stdout, home): the host's own token counts of the run by model, {model: {name: count for each of TOKENS}}, so
    # each is priced at its own model's rate, or None when it reported none: a count it did not report is missing,
    # never estimated
    "tokens": callable,
    # each host fault the harness plants (PLANTED), by name: (command) -> the jail command with that fault planted
    "PLANTS": dict,
    # (skill, path): the one lead line that pins a skill's load in a task run's prompt (doc 12, Proven use), such as
    # "Load the skill NAME at PATH before anything else." It never holds the skill's text (`lead`)
    "pin": callable,
}
# The host faults an adapter plants in its own command (doc 11, Harness faults): its bundled skills turned on, and its
# command tools taken away. Only a fault run passes one to `run`.
PLANTED = ("bundled skills", "no commands")
# A run's tokens: all its input, the parts of that input read from and written to the host's cache, and its output.
TOKENS = ("input", "cache read", "cache write", "output")
SOURCES = ("observed", "inferred")  # the host reported it, or the adapter worked it out
SHA256 = re.compile(r"[0-9a-f]{64}")
# The fields of an entry whose value the harness chooses, with the one test each value passes. A value that passes
# cannot hold the run's text, so the bundle keeps it as it is (evidence.py); any other value is the run's.
FIXED = {"kind": lambda value: value in ENTRIES, "source": lambda value: value in SOURCES,
         "sha256": lambda value: isinstance(value, str) and bool(SHA256.fullmatch(value))}
# Each kind of entry, with every field it holds besides `kind` and `source`, and the one shape each field takes.
ENTRIES = {
    "read": {"path": str},
    "write": {"path": str, "sha256": (str, type(None))},  # None when the host did not report the content
    "command": {"command": str, "exit_code": (int, type(None)), "output": str},
    "blocked": {"action": str, "reason": str},  # an action refused, by the host or by the jail (the reason says)
    "skill": {"name": str},  # the host loaded a skill
    "agent": {"task": str},  # the host started a sub-agent, in the same jail
    "message": {"text": str},  # the last one is the final message
}


class HostError(RuntimeError):
    """The host or its adapter broke the contract. The round stops."""


def entry(kind, source="observed", **fields):
    """One action log entry. A command's output is kept whole, so the scrub always sees a credential whole; the
    grader view never shows it (view.py)."""
    if kind == "command":
        fields.setdefault("output", "")
    return {"kind": kind, "source": source, **fields}


def sha256(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def check_adapter(adapter):
    """Raise HostError naming every way `adapter` differs from CONTRACT."""
    wrong = []
    for name, shape in CONTRACT.items():
        value = getattr(adapter, name, None)
        if not (callable(value) if shape is callable else isinstance(value, shape)):
            wrong.append(f"{name} is missing or not a {getattr(shape, '__name__', shape)}")
    plants = getattr(adapter, "PLANTS", None) or {}
    if sorted(plants) != sorted(PLANTED) or not all(callable(plant) for plant in plants.values()):
        wrong.append(f"PLANTS is not one function for each of {list(PLANTED)}")
    for tool, kind in (getattr(adapter, "TOOLS", None) or {}).items():
        if kind not in powers.TOOLS:
            wrong.append(f"tool {tool} has kind {kind!r}, which is not on the power table")
    if wrong:
        raise HostError(f"adapter {getattr(adapter, 'NAME', adapter)}: " + "; ".join(wrong))


def lead(adapter, skill, path):
    """The lead line that pins the load of `skill` at `path` (its `SKILL.md`, relative to the world) for `adapter`'s
    host, through the adapter's `pin`. Raise HostError unless it is one line that names both the skill and the path
    as whole names: the grader view removes every line that names either in any spelling, whole names among them
    (`view.text`, `view.spelled`), so no page can show it. The test is written here, not taken from `view.spelled`,
    so a fault planted in that pattern cannot hide itself."""
    line = adapter.pin(skill, path)
    if not isinstance(line, str) or line.splitlines() != [line] or not all(
            re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", line, re.ASCII) for word in (skill, path)):
        raise HostError(f"adapter {adapter.NAME}: its pin is not one line naming the skill and its path: {line!r}"[:300])
    return line


def check_log(entries, skills=None):
    """Raise HostError naming every entry that is not exactly one of ENTRIES, and every skill load of a skill not in
    `skills` (the skills the arm installs), when given."""
    if not isinstance(entries, list):
        raise HostError(f"action log: not a list: {entries!r}"[:200])
    wrong = []
    for number, item in enumerate(entries):
        kind = item.get("kind") if isinstance(item, dict) else None
        fields = ENTRIES.get(kind) if isinstance(kind, str) else None
        if fields is None:
            wrong.append(f"entry {number} is not a known kind")
            continue
        if set(item) != {"kind", "source", *fields}:
            wrong.append(f"entry {number} ({item['kind']}) has fields {sorted(item)}")
            continue
        if item["source"] not in SOURCES:
            wrong.append(f"entry {number} has source {item['source']!r}")
        for name, shape in fields.items():
            if isinstance(item[name], bool) or not isinstance(item[name], shape):
                wrong.append(f"entry {number} ({item['kind']}): {name} is not a {shape}")
        if item["kind"] == "write" and item["sha256"] is not None and not SHA256.fullmatch(item["sha256"]):
            wrong.append(f"entry {number} (write): sha256 is not a hash")
        if item["kind"] == "skill" and skills is not None and item["name"] not in skills:
            wrong.append(f"entry {number}: skill {item['name']} was loaded but the case does not declare it")
    if wrong:
        raise HostError("action log: " + "; ".join(wrong))


UNDECLARED = "skill {} is exposed but the case does not declare it"


def check_exposure(adapter, exposure, skills):
    """Raise HostError naming every skill the host exposed that is not in `skills` (the skills the case installs in
    this arm), and every tool that is not one of the adapter's TOOLS."""
    if not isinstance(exposure, dict) or set(exposure) != {"skills", "tools"}:
        raise HostError(f"exposure is not {{'skills': [...], 'tools': [...]}}: {exposure!r}")
    wrong = [UNDECLARED.format(name) for name in exposure["skills"] if name not in skills]
    wrong += [f"tool {name} is exposed but has no kind on the power table"
              for name in exposure["tools"] if name not in adapter.TOOLS]
    if wrong:
        raise HostError("exposure: " + "; ".join(wrong))


def check_tokens(tokens):
    """Raise HostError unless `tokens` is None, or maps each model, a name of at most 200 characters, to a count, a
    whole number from 0, for each of TOKENS and nothing else."""
    def counts(value):
        return isinstance(value, dict) and sorted(value) == sorted(TOKENS) and all(
            isinstance(count, int) and not isinstance(count, bool) and count >= 0 for count in value.values())

    if tokens is not None and not (isinstance(tokens, dict) and tokens and all(
            isinstance(model, str) and 0 < len(model) <= 200 and counts(value) for model, value in tokens.items())):
        raise HostError(f"tokens are not a count for each of {list(TOKENS)} by model: {tokens!r}"[:300])


class Result:
    """One host run: what it printed, how it ended, its checked action log and exposure, the gate's log, how many
    seconds the host ran, and its token counts by model as the host reported them (None when it reported none)."""

    def __init__(self, stdout, stderr, returncode, timed_out, failure, log, exposure, requests, seconds, tokens=None):
        self.stdout, self.stderr, self.returncode, self.timed_out = stdout, stderr, returncode, timed_out
        self.failure, self.log, self.exposure, self.requests = failure, log, exposure, requests
        self.seconds, self.tokens = seconds, tokens


def run(contained, prompt, skills, model=None, timeout=900, plant=None):
    """Run the host of `contained` (a `contain.Containment`, whose adapter also built its environment and gate)
    once, with `prompt` on stdin. `skills` are the skills the arm installs. Return a Result, whose `failure` says
    why the host failed (a void run), or raise HostError when the log or the exposure breaks the contract. A fault
    run names the host fault to `plant` (PLANTED) in the command; a plant that changes nothing raises HostError."""
    adapter = contained.adapter
    check_adapter(adapter)
    command = adapter.jail_command(contained.mode, contained.world, model)
    if plant is not None:
        planted = adapter.PLANTS[plant](list(command))
        if planted == command:
            raise HostError(f"the adapter's {plant} plant leaves its command as it is")
        command = planted
    command = contained.jail(command, program=adapter.CLI)
    contained.audit(adapter.CLI)  # the jail is checked against its list before the host starts
    with contained.gate() as gate:
        started = time.monotonic()
        try:
            done = subprocess.run(command, input=prompt, capture_output=True, text=True, env=contained.env,
                                  timeout=timeout)
            stdout, stderr, returncode, timed_out = done.stdout, done.stderr, done.returncode, False
        except subprocess.TimeoutExpired as expired:
            stdout, stderr, returncode, timed_out = (_text(expired.stdout), _text(expired.stderr), None, True)
        seconds = round(time.monotonic() - started, 3)
    failure = adapter.run_failure(stdout, returncode, timed_out)
    try:
        log = kept(contained, adapter.action_log(stdout, contained.home))
        check_log(log, skills)
        exposure = adapter.exposure(stdout, contained.home)
        if exposure is None and failure is None:  # a host that ran must say what it exposed: silence is not "nothing"
            raise HostError("exposure: the host did not report the skills and tools it exposed")
        if exposure is not None:
            check_exposure(adapter, exposure, skills)
        try:
            tokens = adapter.tokens(stdout, contained.home)
        except Exception as error:  # an adapter that cannot read the counts breaks the contract
            raise HostError(f"tokens: {type(error).__name__}: {error}") from None
        check_tokens(tokens)
    except HostError as error:  # its words may be the host's: they leave the run only scrubbed, while it is there
        raise HostError(scrub.Scrub.of_run(contained).quiet(str(error))) from None
    return Result(stdout, stderr, returncode, timed_out, failure, log, exposure, list(gate.log), seconds, tokens)


def kept(contained, items):
    """The action log a run in `contained` keeps of the entries `items` its host reported, after the run: each entry
    settled (`settle`), and the reads its commands name added (`named`). Every log, a run's or a golden's, is kept
    this one way."""
    log = [settle(item, contained) for item in items]
    return named(contained.world, contained.world_entries, [item for item in log if item is not None])


def settle(item, contained):
    """One entry as the log keeps it, for a run in `contained`. An adapter reports a write that failed as `failed`:
    it is `blocked` when the jail's mount list does not let the run write its path, since the jail then refused it,
    and is otherwise left out, as the world diff shows what happened. A path inside the world is written relative to
    it, as every host's log then says it."""
    if not isinstance(item, dict):
        return item
    world = contained.world
    if item.get("kind") == "failed":
        path = os.path.normpath(os.path.join(world, str(item.get("path", ""))))  # an absolute path stays as it is
        # The nearest mount above the path is the one the jail applies; only `rw` and `tmpfs` mounts are writable.
        above = [m for m in contained.mounts(contained.adapter.CLI)
                 if (path + "/").startswith(m.path.rstrip("/") + "/")]
        if above and max(above, key=lambda m: len(m.path)).how in ("rw", "tmpfs"):
            return None
        return entry("blocked", item.get("source", "observed"), action=str(item.get("action", "")),
                     reason=f"the jail does not let a {contained.mode} run write it: {item.get('reason', '')}")
    path = item.get("path")
    if isinstance(path, str) and (path + "/").startswith(str(world) + "/"):
        return {**item, "path": path[len(str(world)) + 1:] or "."}
    return item


# Where a file's name ends and starts in a command: at its edge, a space, a quote, a shell operator or a bracket.
EDGE = r"""\s'"`;&|<>(){}="""


def named(world, before, log):
    """`log` with an inferred read, right after each command, of every world file the command names. Each command's
    reads depend on that command alone, never on what the log read before, so the grader view drops them with their
    command (`part_of_command`) and no hidden entry changes what a shown command reads; a file its adapter already
    inferred there is not added twice. The view shows each file's inferred read once. Whether a command read a file it
    names is never known, so a check never decides on it (doc 11, Harness faults); without an entry, a check would
    wrongly decide the file was not read. One rule decides what a command names, never how a shell would resolve it: a
    file of the world before the run (`before`, its manifest) or after it is named when its name stands whole in the
    command, or a wildcard word matches its name, or, when the word holds a folder, its path (`_read_from`). Two
    files of one name are both named. A link is no file, and a folder named alone names none of its files."""
    try:
        after = manifest.manifest(world, skip=(".git",), other=True)
    except manifest.Unreadable:  # the bundle reports a world it cannot read; the files before still count
        after = {}
    files = sorted({p for entries in (before, after) for p, e in entries.items()
                    if manifest.is_file(e) and p.split("/")[0] != ".git"})
    found, root = [], os.path.normpath(str(world))
    for number, item in enumerate(log):
        found.append(item)
        if not isinstance(item, dict) or item.get("kind") != "command" or not isinstance(item.get("command"), str):
            continue
        own = set()  # the inferred reads its adapter put right after it
        for later in log[number + 1:]:
            if not part_of_command(later):
                break
            if later.get("kind") == "read":
                own.add(os.path.normpath(str(later.get("path"))))
        names = naming(item["command"], root)
        found += [entry("read", "inferred", path=path) for path in files if names(path) and path not in own]
    return found


def naming(command, root):
    """The one rule of `named`: a test of whether `command`, run in the world at `root`, names a world path. The
    grader view keeps by it the reads of the part of a command it shows."""
    words = re.split(rf"[{EDGE}]+", command)
    globs = [w for w in words if any(c in w for c in "*?[")]
    bare = [glob for glob in globs if "/" not in glob]  # matched by name; a glob with a folder, by path
    paths = {form for glob in globs if "/" in glob for form in _read_from(root, glob)}
    ends = {w[i + 1:] for w in words for i in range(-1, len(w)) if i < 0 or w[i] == "/"}  # each word after a /

    def names(path):
        name = path.rsplit("/", 1)[-1]
        whole = name in ends if not re.search(rf"[{EDGE}]", name) else re.search(
            rf"(?:^|[{EDGE}/]){re.escape(name)}(?=$|[{EDGE}])", command)  # a name with an edge in it
        return bool(whole) or any(fnmatch.fnmatchcase(f"{root}/{path}", form) for form in paths) or any(
            fnmatch.fnmatchcase(name, glob) for glob in bare)
    return names


def _read_from(root, glob):
    """The patterns of world paths a wildcard word with a folder may name: the word read from the world (./src/*.py,
    /world/src/*.py, ../world/src/*.py), and its part after its last parent step, as the end of a path, since a
    command may run from any folder below the world (cd docs/x && cat ../../src/*.py). A **/ may match no folder."""
    parts = os.path.normpath(glob).split("/")
    rest = "/".join(parts[max((i for i, part in enumerate(parts) if part == ".."), default=-1) + 1:])
    forms = {os.path.normpath(os.path.join(root, glob))}
    if rest and not os.path.isabs(rest):
        forms |= {f"{root}/{rest}", f"{root}/*/{rest}"}
    return {form.replace("**/", "*") for form in forms}  # fnmatch's * spans folders, so each **/ may match none


def part_of_command(item):
    """Whether a log entry is part of the command before it: an inferred read or skill load standing right after the
    command, as `named` and each adapter put them. The grader view drops them with their command."""
    return isinstance(item, dict) and item.get("source") == "inferred" and item.get("kind") in ("read", "skill")


def _text(data):
    return data.decode(errors="replace") if isinstance(data, bytes) else data or ""
