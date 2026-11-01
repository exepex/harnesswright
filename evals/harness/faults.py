"""Harness faults: the planted faults the harness must catch (doc 11, Harness faults), from one catalogue.

One rule: a fault is planted as its entry in `evals/faults/harness.json` says, with names and places a seed chooses,
and the harness's own gate runs on it unchanged. It is caught only when that gate gives the one outcome its plant
names; any other outcome, an error included, is a miss. Where a host runs, the harness itself checks the fault from
inside the run's jail, so what the host chose to do never decides it. The README's "Harness faults" says more.

Standard library only.
"""

import json
import os
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

import cases
import contain
import evidence
import host
import lint
import manifest
import probes
import scrub
import skills
import world
from cases import REPO

CATALOGUE = REPO / "evals" / "faults" / "harness.json"
FIELDS = {"id": str, "row": str, "prompt": str, "names": list}  # all an entry may hold; `id` and `row` it must
HOST_KEYS = set(contain.BASE_KEYS + contain.CA_KEYS + contain.RUN_KEYS)  # passed by design, so never planted
CANARY = ".hw-canary-"


class FaultError(ValueError):
    """The catalogue is not what this module reads."""


class Missed(RuntimeError):
    """A plant could not show its fault caught, for the reason given: the fault is a miss."""


class Setup:
    """What faults run against: a host's `adapter`, a clean `case` of the skill in `skill_dir`, the folder `root`
    (outside the repository) where plants, runs and bundles go, the host's tools and drift record (`probes.drift`),
    and `containment`, passed to `contain.Containment` (the operator's environment, home and host paths)."""

    def __init__(self, adapter, case, skills_root, root, drift, skill_dir=None, prompts=None, model=None,
                 host_version="unknown", timeout=900, repo=REPO, **containment):
        self.adapter, self.case, self.drift, self.model = adapter, case, drift, model
        self.skills_root, self.root = Path(skills_root), Path(root)
        self.skill_dir = Path(skill_dir) if skill_dir else self.skills_root / case.skill
        self.prompts, self.host_version, self.timeout, self.repo = prompts or {}, host_version, timeout, repo
        self.containment = containment
        self.bundles = []  # every bundle a fault run stored, for the judges to read
        self.made = []  # every containment a fault made, whose scrub every reason passes through
        self.root.mkdir(parents=True, exist_ok=True)

    def folder(self):
        """A new folder under `root` whose name says nothing about the fault or the arm."""
        return Path(tempfile.mkdtemp(prefix="f-", dir=self.root))

    def prompt(self, fault, planted):
        if fault["id"] in self.prompts:
            return self.prompts[fault["id"]](planted)
        return fault["prompt"].replace("{skill}", self.case.skill)


def load(path=CATALOGUE):
    """The catalogue's entries. Raise FaultError unless each holds only the fields of FIELDS, with `id` and `row`,
    the ids are exactly the plants of PLANTS, and every plant that runs a host has its prompt."""
    try:
        entries = json.loads(Path(path).read_text())["faults"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise FaultError(f"{path}: not a fault catalogue: {error}") from None
    problems = []
    for number, entry in enumerate(entries if isinstance(entries, list) else [None]):
        if not isinstance(entry, dict):
            problems.append(f"entry {number} is not an object")
            continue
        wrong = sorted(k for k, v in entry.items() if k not in FIELDS or not isinstance(v, FIELDS[k]))
        missing = sorted({"id", "row"} - set(entry))
        if wrong or missing:
            problems.append(f"entry {number}: fields {wrong} are not allowed or not of their shape, {missing} missing")
        elif entry["id"] in PLANTS and PLANTS[entry["id"]][2] and "prompt" not in entry:
            problems.append(f"{entry['id']}: its plant runs a host, so it needs a prompt")
    ids = [e.get("id") for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
    if sorted(ids) != sorted(PLANTS):
        problems.append(f"the ids {sorted(ids)} are not exactly the plants {sorted(PLANTS)}")
    if problems:
        raise FaultError(f"{path}: " + "; ".join(problems))
    return entries


def run(fault, setup, seed, place=None):
    """Plant `fault` (a catalogue entry) at `place`, one of its plant's places, or at the one `seed` chooses, and
    run its gate. Return {"id", "place", "caught", "reason", "bundles"}: `reason` says why it was missed, and
    `bundles` are the folders of the runs' stored bundles, from which the judges decide each was caught."""
    plant, places, _ = PLANTS[fault["id"]]
    if not getattr(setup.adapter, "CREDENTIAL_FILES", ()):
        places = tuple(p for p in places if p != "credential")  # a host with no credential file has no such place
    rng, stored, made = random.Random(seed), len(setup.bundles), len(setup.made)
    place = place or rng.choice(places)
    if place not in places:
        raise FaultError(f"{fault['id']}: {place!r} is not one of its places {places}")
    try:
        reason = plant(setup, fault, rng, place)
    except Missed as error:
        reason = str(error)
    except Exception as error:  # an outcome the plant does not name, whatever it is, is a miss
        reason = f"the gate gave another outcome: {type(error).__name__}: {error}"
    if reason is not None:  # one way out for a reason: any run's words in it may hold a canary or a credential
        runs = setup.made[made:]
        quiet = scrub.Scrub([t for c in runs for t in c.tokens], [v for c in runs for v in scrub.credentials(c)])
        reason = quiet.quiet(reason)
    return {"id": fault["id"], "place": place, "caught": reason is None, "reason": reason,
            "bundles": setup.bundles[stored:]}


def _copy(setup):
    """A copy of the setup's case in a new folder, to plant in. Return (the copy's folder, its case.json data)."""
    folder = setup.folder() / "cases" / setup.case.id
    shutil.copytree(setup.case.folder, folder, symlinks=True)
    return folder, json.loads((folder / "case.json").read_text())


def _contained(setup, case, tokens=(), folder=None, **options):
    """The containment of the without-skill run of `case`, built and proved as a round builds it, in `folder` or a
    new one, and the skills that arm installs (its siblings), which its host may expose."""
    folder = folder or setup.folder()
    base = world.build(case, setup.adapter, folder / "a", setup.skills_root)
    other = world.build(case, setup.adapter, folder / "b", setup.skills_root, True, setup.skill_dir)
    world.prove(case, setup.adapter, base, other, setup.skills_root, setup.skill_dir)
    options = {**setup.containment, **options}
    options["tokens"] = [*options.get("tokens", ()), *tokens]
    contained = contain.Containment(setup.adapter, case.kind, base.path, manifest.manifest(base.path),
                                    root=folder / "run", **options)
    setup.made.append(contained)
    return contained, [install.name for install in base.installs]


def _run(setup, fault, case, planted, tokens=(), folder=None, **options):
    """One without-skill run of `case` with the fault planted. Return the folder of its bundle, stored and read
    back, and its containment. A canary that reaches its output raises `scrub.Leak`, and a jail that fails its
    audit raises `contain.ContainmentError`."""
    contained, installed = _contained(setup, case, tokens, folder, **options)
    result = host.run(contained, setup.prompt(fault, planted), skills=installed, model=setup.model,
                      timeout=setup.timeout)
    if result.failure:  # a host that did not run never met the fault
        raise Missed(f"the host failed, so the fault was never met: {result.failure}")
    layer = evidence.overlay(case, setup.adapter, setup.skills_root, setup.skill_dir)
    record, blobs = evidence.collect(contained, result, case, "without_skill", layer, setup.drift,
                                     setup.host_version, setup.model)
    out = evidence.store(record, blobs, setup.folder() / "bundle")
    setup.bundles.append(str(out))
    return out, contained


def _decoy(setup, folder):
    return probes.decoy_home(setup.adapter, folder, setup.containment.get("operator_home"))


# Run in a run's own jail by the harness: given paths on stdin, it prints the ones the jail lets it stat or read.
SEEN = r"""
import json, os, sys
seen = []
for path in json.load(sys.stdin):
    try:
        os.lstat(path)
    except OSError:
        continue
    seen.append(path)
print(json.dumps(seen))
"""


# Run the same way: it prints the environment the jail gives a program.
ENVIRONMENT = "import json, os\nprint(json.dumps(dict(os.environ)))\n"


def jailed(contained, program, data=None):
    """What `program`, a Python text the harness runs in the jail of `contained` with its host's mounts and
    environment, prints as JSON: decided by the harness, whatever the host chose to do."""
    command = contained.jail([contain.PYTHON, "-I", "-c", program], program=contained.adapter.CLI)
    with contained.gate():
        done = subprocess.run(command, input=json.dumps(data), capture_output=True, text=True, env=contained.env,
                              timeout=120)
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError:
        raise Missed(f"the harness could not look inside the jail: {done.stderr.strip()[-300:]}") from None


def outside(setup, fault, rng, place):
    """A canary file and a copy of the skill holding a canary, at a place outside the run: beside its world, in a
    decoy operator home, in another run's folder, in the machine's temporary folder or in the repository checkout.
    One rule decides it: the harness looks for every planted path from inside the run's own jail and finds none.
    The run itself must also pass its audit, end without failing, and keep every canary out of its output (one
    that reaches it raises `scrub.Leak`). What the host chose to look at never decides it."""
    folder = setup.folder()  # the run's own folder: its world is built in it, at `a`
    options = {"folder": folder}
    if place == "operator":
        options["operator_home"] = target = _decoy(setup, folder / "home")
    elif place == "machine":
        target = Path(tempfile.mkdtemp(prefix="f-"))  # the machine's own temporary folder, not the run's
    elif place == "repository":
        target = Path(tempfile.mkdtemp(prefix=".hw-fault-", dir=REPO))  # removed below, never committed
    else:
        target = folder / "next" if place == "beside" else setup.folder() / "run" / "a"
    try:
        planted = contain.plant_canaries([target])
        token = contain.new_token()
        copy = target / rng.choice(["skills", ".agents", "share"]) / setup.case.skill
        for relative, data in skills.skill_files(setup.skill_dir, setup.case.skill)[0].items():  # tracked files
            (copy / relative).parent.mkdir(parents=True, exist_ok=True)
            (copy / relative).write_bytes(data)
        (copy / "SKILL.md").write_text((copy / "SKILL.md").read_text() + f"\n{token}\n")
        planted[token] = str(copy / "SKILL.md")
        paths = sorted(planted.values()) + [str(target), str(copy)]
        _, contained = _run(setup, fault, setup.case, {"paths": sorted(planted.values()),
                                                       "folders": [str(target), str(copy)]},
                            tokens=list(planted), **options)
        found = jailed(contained, SEEN, paths)
    finally:
        if place in ("machine", "repository"):
            shutil.rmtree(target, ignore_errors=True)
    return f"the run's jail can find {len(found)} planted path(s)" if found else None


def inside(setup, fault, rng, place):
    """A canary in a place the run sees: its world, a host path the operator names, or a credential file copied
    from a decoy home. Caught when the audit refuses the run for it, and passes the same run without it."""
    options, token = {}, contain.new_token()
    if place == "credential":
        names = list(setup.adapter.CREDENTIAL_FILES)
        home = _decoy(setup, setup.folder() / "home")
        relative = rng.choice(names)
        (home / relative).parent.mkdir(parents=True, exist_ok=True)
        try:  # never through a link, which the decoy keeps as a link and which leads to the operator's own file
            handle = os.open(home / relative, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        except OSError as error:
            raise Missed(f"the credential file {relative} cannot be planted without following a link: "
                         f"{error.strerror}") from None
        with os.fdopen(handle, "a") as opened:
            opened.write(f"\n{token}\n")
        options["operator_home"] = home
    case = setup.case
    if place == "world":
        folder, _ = _copy(setup)
        (folder / "world" / f"notes-{rng.randrange(16 ** 6):06x}.md").write_text(f"{token}\n")
        case = cases.Case(folder, setup.case.skill)
    if place == "host path":
        named = setup.folder() / "tool"
        named.mkdir()
        (named / f"{CANARY}{rng.randrange(16 ** 6):06x}").write_text(f"{token}\n")
        options["host_paths"] = [*setup.containment.get("host_paths", ()), named]
    _contained(setup, case, **options)[0].audit(setup.adapter.CLI)  # the control: the same run, no canary listed
    try:
        _contained(setup, case, [token], **options)[0].audit(setup.adapter.CLI)
    except contain.ContainmentError as error:
        return None if "a canary token is in" in str(error) else f"the audit refused it for another reason: {error}"
    return "the audit passed a run that can see a canary"


def environment(setup, fault, rng, place):
    """Session, memory and credential values in the operator's environment: names from the entry the adapter does
    not pass by design, chosen by the seed, each with a fresh value. The harness itself dumps the environment from
    inside the run's jail, so the result never rests on what the host chose to print. Caught when the dump holds
    none of the planted names, the run's scrub removes every planted value and credential from that dump, and the
    run's bundle holds none of them either."""
    passed = HOST_KEYS | set(getattr(setup.adapter, "ENV_KEYS", ()))
    names = sorted(n for n in fault["names"] if n not in passed)
    chosen = rng.sample(names, min(3, len(names)))
    decoys = {name: f"hw-{rng.randbytes(12).hex()}" for name in chosen}
    given = setup.containment.get("operator_env")
    env = {**(os.environ if given is None else given), **decoys}  # as `contain.Containment` reads it
    out, contained = _run(setup, fault, setup.case, {"names": chosen}, operator_env=env)
    dump = jailed(contained, ENVIRONMENT)
    leaked = sorted(set(chosen) & set(dump))
    if leaked:
        return f"the run's environment holds {leaked}"
    values = [*decoys.values(), *scrub.credentials(contained)]  # a base URL is passed on and is no secret
    scrubbed = scrub.Scrub.of_run(contained).text(json.dumps(dump)).encode()
    stored = [scrubbed, (out / "bundle.json").read_bytes(), *(p.read_bytes() for p in (out / "blobs").iterdir())]
    if any(value.encode() in data for value in values for data in stored):
        return "a planted value or a credential reached the bundle"
    return None


def _lint(setup, folder):
    """The lint's problems for the case in `folder`, as `lint.lint_skill` lints a skill's cases."""
    return lint.lint_skill(setup.case.skill, setup.adapter, folder.parent, setup.skills_root, setup.repo,
                           setup.skill_dir)


def _refused(setup, plant, rule):
    """Copy the case, check that the lint passes it, plant with `plant(folder, data)`, which returns the key of the
    place it planted (a world path or `<prompt>`), and check that the lint refuses that place by `rule`, the words
    of the one problem the plant must cause. Another problem at that place is not this fault caught."""
    folder, data = _copy(setup)
    control = _lint(setup, folder)
    if control:
        return f"the clean case does not pass the lint, so the fault proves nothing: {control[0]}"
    key = plant(folder, data)
    (folder / "case.json").write_text(json.dumps(data))
    found = _lint(setup, folder)
    if any(problem.startswith(f"{setup.case.id}: {key}: ") and rule in problem for problem in found):
        return None
    return f"the lint did not refuse {key} as {rule!r}: {found[:2]}"


def _put(folder, data, rng, place, text):
    """Put `text` at `place`: a new world file, the end of an existing one, or the end of the prompt."""
    if place == "prompt":
        data["prompt"] += f" {text}"
        return cases.PROMPT_KEY
    files = sorted(p for p in (folder / "world").rglob("*")
                   if p.is_file() and not p.is_symlink() and lint.plain(p.read_bytes()) is not None)
    if place == "existing" and files:
        path = rng.choice(files)
        path.write_text(path.read_text() + f"\n{text}\n")
    else:
        path = folder / "world" / f"notes-{rng.randrange(16 ** 6):06x}.md"
        path.write_text(f"# Notes\n\n{text}\n")
    return str(path.relative_to(folder / "world"))


def names(setup, fault, rng, place):
    """The skill's name, its path, or a run of its own text (its fingerprint) at a place the run sees. Caught when
    the lint refuses that place."""
    where, what = place.split("/")
    skill = setup.case.skill
    if what == "name":
        text = f"Ask {skill} for help here."
    elif what == "path":
        text = f"See {setup.case.skill_rel} first."
    else:
        # A run of the skill's text that is its own, after the project text the lint excuses (its upstream source
        # and the standard licences), as the lint finds it.
        repo = Path(setup.repo)
        project = lint.texts(repo / "evals" / "skills" / skill / "upstream") + lint.texts(repo.joinpath(*lint.LICENCES))
        files, _ = skills.skill_files(setup.skill_dir, skill)
        own = sorted(lint.all_runs([d.decode("utf-8", "replace") for d in files.values()], {lint.RUN})
                     - lint.all_runs(project, {lint.RUN}))
        if not own:
            raise Missed("the skill has no text of its own for the lint to protect, so no fingerprint can be planted")
        text = rng.choice(own)
    rule = "of the skill's own text" if what == "fingerprint" else "names the skill"
    return _refused(setup, lambda folder, data: _put(folder, data, rng, where, text), rule)


def tells(setup, fault, rng, place):
    """A test-tell word, a run of the measuring kit's own text, or a whole eval file (a copy of this catalogue) at a
    place the run sees. Caught when the lint refuses that place."""
    where, what = place.split("/")
    if what == "eval file":
        def plant(folder, data):
            name = f"plan-{rng.randrange(16 ** 6):06x}.json"
            shutil.copyfile(Path(setup.repo) / CATALOGUE.relative_to(REPO), folder / "world" / name)
            return name
        return _refused(setup, plant, "holds eval text")
    if what == "word":
        text = f"Keep the {rng.choice(lint.TELLS)} notes short."
    else:
        rows = [w for e in load(Path(setup.repo) / CATALOGUE.relative_to(REPO))
                for w in [e.get("prompt", "").split()] if len(w) >= lint.RUN]
        said = rng.choice(rows)
        start = rng.randrange(len(said) - lint.RUN + 1)
        text = " ".join(said[start:start + lint.RUN])
    rule = "test-tell word" if what == "word" else "holds eval text"
    return _refused(setup, lambda folder, data: _put(folder, data, rng, where, text), rule)


SPOTS = ("file", "existing", "prompt")
# Each plant: its function, its places, and whether it runs a host (and so needs a prompt).
PLANTS = {
    "outside": (outside, ("beside", "operator", "other run", "machine", "repository"), True),
    "inside": (inside, ("world", "host path", "credential"), False),
    "environment": (environment, ("operator env",), True),
    "names": (names, tuple(f"{s}/{w}" for s in SPOTS for w in ("name", "path", "fingerprint")), False),
    "tells": (tells, tuple(f"{s}/{w}" for s in SPOTS for w in ("word", "kit text")) + ("file/eval file",), False),
}
