"""Harness faults: the planted faults the harness must catch (doc 11, Harness faults), from one catalogue.

One rule: a fault is planted as its entry in `evals/faults/harness.json` says, at a place a seed chooses, and the
harness's own gate runs on it unchanged. It is caught only when that gate gives the one outcome its plant names; any
other outcome, an error included, is a miss. The harness, never the host, decides it (README, "Harness faults").

Standard library only.
"""

import json
import os
import random
import shutil
import tempfile
import urllib.parse
from pathlib import Path

import cases
import contain
import evidence
import host
import lint
import look
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


class Caught(str):
    """What a gate saw when it caught its fault, returned by a plant whose fault stops the run before it stores a
    bundle: the outcome the gate named, kept for the judges as the evidence of the catch."""


class Setup:
    """What faults run against: a host's `adapter`, a clean `case` of the skill in `skill_dir`, the folder `root`
    (outside the repository) for plants, runs and bundles, the drift record (`probes.drift`), the `prompts` that
    replace the entries' own (fault id: function of what was planted) and options for `contain.Containment`."""

    def __init__(self, adapter, case, skills_root, root, drift, skill_dir=None, prompts=None, model=None,
                 host_version="unknown", timeout=900, repo=REPO, **containment):
        self.adapter, self.case, self.drift, self.model = adapter, case, drift, model
        self.skills_root, self.root = skills.library(skills_root), Path(root)  # {name: folder}
        self.skill_dir = Path(skill_dir) if skill_dir else self.skills_root.get(case.skill)
        self.prompts, self.host_version, self.timeout, self.repo = prompts or {}, host_version, timeout, repo
        self.containment = containment
        self.bundles = []  # every bundle a fault run stored, for the judges to read
        self.made = []  # every containment a fault made, whose scrub every reason passes through
        self.root.mkdir(parents=True, exist_ok=True)

    def folder(self):
        """A new folder under `root` whose name says nothing about the fault or the arm."""
        return Path(tempfile.mkdtemp(prefix="f-", dir=self.root))

    def prompt(self, fault, planted):
        """The prompt of `fault`'s run: its entry's, with `{skill}` and each text the plant chose filled in."""
        if fault["id"] in self.prompts:
            return self.prompts[fault["id"]](planted)
        text = fault["prompt"].replace("{skill}", self.case.skill)
        for key, value in planted.items():
            text = text.replace(f"{{{key}}}", value) if isinstance(value, str) else text
        return text


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
        elif entry["id"] in plants() and plants()[entry["id"]][2] and "prompt" not in entry:
            problems.append(f"{entry['id']}: its plant runs a host, so it needs a prompt")
    ids = [e.get("id") for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
    if sorted(ids) != sorted(plants()):
        problems.append(f"the ids {sorted(ids)} are not exactly the plants {sorted(plants())}")
    if problems:
        raise FaultError(f"{path}: " + "; ".join(problems))
    return entries


def run(fault, setup, seed, place=None):
    """Plant `fault` (a catalogue entry) at `place`, one of its plant's places, or at the one `seed` chooses, and
    run its gate. Return {"id", "place", "caught", "reason", "seen", "bundles"}: `reason` says why it was missed,
    `seen` is what the gate saw when it caught a fault that stops its run (`Caught`), and `bundles` are the folders
    of the runs' stored bundles. From these the judges decide each was caught."""
    plant, places, _ = plants()[fault["id"]]
    files = getattr(setup.adapter, "CREDENTIAL_FILES", ())
    has = {"credential": files, "key": files or getattr(setup.adapter, "ENV_KEYS", ())}
    places = tuple(p for p in places if has.get(p, True))  # a host has no place for a sign-in it does not use
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
    caught = reason is None or isinstance(reason, Caught)
    if reason is not None:  # one way out for its words: any run's words may hold a canary or a credential
        runs = setup.made[made:]
        given = setup.containment.get("operator_env")  # known before any containment is made, which may fail
        named = _secrets(os.environ if given is None else given, getattr(setup.adapter, "ENV_KEYS", ()))
        named += [v for c in runs for v in scrub.credentials(c)]
        quiet = scrub.Scrub([t for c in runs for t in c.tokens], named)
        reason = quiet.quiet(reason)
    return {"id": fault["id"], "place": place, "caught": caught, "reason": None if caught else reason,
            "seen": reason if caught else None, "bundles": setup.bundles[stored:]}


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


def _run(setup, fault, case, planted, tokens=(), folder=None, plant=None, **options):
    """One without-skill run of `case` with the fault planted, and the host fault `plant` when given (`host.run`).
    Return the folder of its bundle, stored and read back, and its containment. A canary that reaches its output
    raises `scrub.Leak`, and a jail that fails its audit raises `contain.ContainmentError`."""
    contained, installed = _contained(setup, case, tokens, folder, **options)
    result = host.run(contained, setup.prompt(fault, planted), skills=installed, model=setup.model,
                      timeout=setup.timeout, plant=plant)
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


def outside(setup, fault, rng, place):
    """A canary file and a copy of the skill holding a canary, outside the run: beside its world, in a decoy
    operator home, in another run's folder, in the machine's temporary folder or in the repository. Caught when the
    harness, from inside the run's jail, finds no planted path, and the run passes its audit, ends without failing
    and keeps every canary out of its output (one that reaches it raises `scrub.Leak`)."""
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
        shown = {"paths": sorted(planted.values()), "folders": [str(target), str(copy)]}
        _, contained = _run(setup, fault, setup.case, shown, tokens=list(planted), **options)
        found = look.look(contained, look.SEEN, shown["paths"] + shown["folders"])
    finally:
        if place in ("machine", "repository"):
            shutil.rmtree(target, ignore_errors=True)
    return f"the run's jail can find {len(found)} planted path(s)" if found else None


def inside(setup, fault, rng, place):
    """A canary in its world, a host path the operator names or a credential file copied from a decoy home: places
    the run sees. Caught when the audit refuses the run for it, and passes the same run without it."""
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
    not pass by design, chosen by the seed, each with a fresh value. Caught when the environment the harness dumps
    from inside the run's jail holds none of the names, and neither its scrubbed dump nor the run's bundle holds a
    planted value or a credential."""
    passed = HOST_KEYS | set(getattr(setup.adapter, "ENV_KEYS", ()))
    names = sorted(n for n in fault["names"] if n not in passed)
    chosen = rng.sample(names, min(3, len(names)))
    decoys = {name: f"hw-{rng.randbytes(12).hex()}" for name in chosen}
    given = setup.containment.get("operator_env")
    env = {**(os.environ if given is None else given), **decoys}  # as `contain.Containment` reads it
    out, contained = _run(setup, fault, setup.case, {"names": chosen}, operator_env=env)
    dump = look.look(contained, look.ENVIRONMENT)
    leaked = sorted(set(chosen) & set(dump))
    if leaked:
        return f"the run's environment holds {leaked}"
    values = [*decoys.values(), *_secrets(env, getattr(setup.adapter, "ENV_KEYS", ()))]
    scrubbed = scrub.Scrub.of_run(contained).text(json.dumps(dump)).encode()
    stored = [scrubbed, (out / "bundle.json").read_bytes(), *(p.read_bytes() for p in (out / "blobs").iterdir())]
    if any(value.encode() in data for value in values for data in stored):
        return "a planted value or a credential reached the bundle"
    return None


def _secrets(env, keys):
    """The credentials of `keys` in `env`, worked out here and never by the scrub the fault tests: a value as it is,
    or for a URL its password, else its user (a token), so a base URL with neither is no secret."""
    urls = {v: urllib.parse.urlsplit(v) for v in (env.get(k, "") for k in keys) if "://" in v}
    found = [(u.password or u.username) if v in urls and (u := urls[v]) else v for v in (env.get(k, "") for k in keys)]
    return [spelling for v in found if v for spelling in {v, urllib.parse.unquote(v)}]  # as written, and decoded


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
        # A run of the skill's own text, after what the lint excuses (its upstream source and the licences).
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
        allowed = {" ".join(lint.words(w)) for ws in setup.case.allow_words.values() for w in ws}  # a case's own
        text = f"Keep the {rng.choice([t for t in lint.TELLS if t not in allowed])} notes short."
    else:
        rows = [w for e in load(Path(setup.repo) / CATALOGUE.relative_to(REPO))
                for w in [e.get("prompt", "").split()] if len(w) >= lint.RUN]
        said = rng.choice(rows)
        start = rng.randrange(len(said) - lint.RUN + 1)
        text = " ".join(said[start:start + lint.RUN])
    rule = "test-tell word" if what == "word" else "holds eval text"
    return _refused(setup, lambda folder, data: _put(folder, data, rng, where, text), rule)


def plants():
    """Every plant, by id: this module's, the host faults' (`host_faults.py`) and the grading faults'
    (`grading_faults.py`, `grader_faults.py`), which use this module."""
    import grader_faults
    import grading_faults
    import host_faults
    return {**PLANTS, **host_faults.PLANTS, **grading_faults.PLANTS, **grader_faults.PLANTS}


SPOTS = ("file", "existing", "prompt")
# Each plant: its function, its places, and whether it runs a case on a host (so needs a prompt, and stores a bundle).
PLANTS = {
    "outside": (outside, ("beside", "operator", "other run", "machine", "repository"), True),
    "inside": (inside, ("world", "host path", "credential"), False),
    "environment": (environment, ("operator env",), True),
    "names": (names, tuple(f"{s}/{w}" for s in SPOTS for w in ("name", "path", "fingerprint")), False),
    "tells": (tells, tuple(f"{s}/{w}" for s in SPOTS for w in ("word", "kit text")) + ("file/eval file",), False),
}
