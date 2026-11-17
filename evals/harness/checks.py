"""Script checks (doc 11, Scoring): the one way a check decides an expectation from a run's bundle.

One rule: a check is a function of the full bundle and its arguments that returns `pass` or `fail` with a reason, or
`undecidable`. It reads the bundle only through `Bundle`, whose one door to the action log refuses evidence the
host did not observe: when an entry of a kind the check reads is tagged inferred, the check is `undecidable` and
the expectation goes to the graders with the command list. The checks are the `CHECKS` of the modules in
`evals/checks/`, each with an allow list of its arguments, and each has answer keys in `evals/checks/keys/<name>/`:
fixtures that must give `pass`, `fail` or `undecidable`, run in the unit tests. A check that cannot run, or
arguments outside its list, raise CheckError: a broken check stops the round, it never passes.

Standard library only.
"""

import fnmatch
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import evidence
import manifest
from cases import REPO

LIBRARY = REPO / "evals" / "checks"
KEYS = LIBRARY / "keys"
OUTCOMES = ("pass", "fail", "undecidable")
KEY_FIELDS = {"args", "outcome", "before", "after", "log", "final_message"}


class CheckError(RuntimeError):
    """A check that cannot decide as this module says: unknown, broken, or given arguments outside its list."""


class Undecidable(Exception):
    """Raised inside a check when the evidence it needs is not the host's own, with the reason."""


class Inferred(Undecidable):
    """Raised when the evidence a check reads is inferred, not observed."""


@dataclass(frozen=True)
class Check:
    """One check: `decide(bundle, **args)` returns (outcome, reason). `args` maps each argument to its shape, a
    function that says whether a value fits; the names in `optional` may be left out."""
    decide: object
    args: dict
    optional: tuple = field(default=())
    about: str = ""


class Bundle:
    """What a check may read of one run: the files after, the world diff, the action log by kind and the final
    message. Built from a stored bundle (`load`) or from an answer key (`key`), the same way."""

    def __init__(self, record, blob):
        self.files = record["files_after"]
        self.changes = record["diff"]
        self.final_message = record["final_message"]
        self._log, self._blob = record["log"], blob

    @classmethod
    def load(cls, folder):
        return cls(*evidence.load(folder))

    @classmethod
    def key(cls, data):
        """A bundle from an answer key's `before` and `after` worlds ({path: text}, where a path ending in `/` is a
        folder and a value {"link": target} a link), `log` and `final_message`. Its files after and diff are made
        from manifest entries, every folder above a path included, as `evidence.collect` makes them."""
        blobs, before, after = {}, {}, {}
        for side, files in ((before, data.get("before", {})), (after, data.get("after", {}))):
            for path, text in files.items():
                parts = path.rstrip("/").split("/")
                side.update({"/".join(parts[:end]): "dir" for end in range(1, len(parts))})
                if path.endswith("/") or isinstance(text, dict):
                    side[path.rstrip("/")] = "dir" if path.endswith("/") else f"link {text['link']}"
                    continue
                raw = text.encode()
                blobs[hashlib.sha256(raw).hexdigest()] = raw
                side[path] = f"file {hashlib.sha256(raw).hexdigest()}"
        record = {"files_after": after, "diff": evidence.diff(before, after), "log": data.get("log", []),
                  "final_message": data.get("final_message")}
        return cls(record, blobs.__getitem__)

    def text(self, path):
        """The text of the file at `path` after the run, or None when there is no file there."""
        entry = self.files.get(path)
        if entry is None or not manifest.is_file(entry):
            return None
        return self._blob(entry.split(" ")[1]).decode("utf-8", errors="replace")

    def entries(self, kind):
        """The log entries of `kind`. Raise Inferred, an Undecidable, when any of them is inferred: no check decides
        on it."""
        found = [item for item in self._log if item["kind"] == kind]
        inferred = [item for item in found if item["source"] != "observed"]
        if inferred:
            raise Inferred(f"{len(inferred)} {kind} entries are inferred, not observed: "
                           f"{json.dumps(inferred[0])[:200]}")
        return found


def is_globs(value):
    """Whether `value` is a list of globs for `matches`: at least one, none empty."""
    return isinstance(value, list) and bool(value) and all(isinstance(v, str) and v for v in value)


def matches(path, patterns):
    """Whether `path` matches any of the glob `patterns`, where `*` crosses folders."""
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def library(folder=LIBRARY):
    """{name: Check} from the `CHECKS` of every module in `folder`. CheckError when a name repeats or a module
    does not hold Checks."""
    found, saved = {}, sys.dont_write_bytecode
    for path in sorted(Path(folder).glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"checks_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        sys.dont_write_bytecode = True  # no bytecode in the library's folder, which is the kit's (kit.py)
        try:
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = saved
        given = getattr(module, "CHECKS", None)
        if not isinstance(given, dict) or not all(isinstance(c, Check) for c in given.values()):
            raise CheckError(f"{path.name}: CHECKS is not a mapping of names to Checks")
        for name, check in given.items():
            if name in found:
                raise CheckError(f"{path.name}: the check {name} is defined twice")
            found[name] = check
    return found


def validate(name, args, checks=None):
    """The check `name`, when `args` fit its list: the one test of a check and its arguments, which the lint runs
    on every case and `decide` on every call. CheckError otherwise."""
    checks = library() if checks is None else checks
    if name not in checks:
        raise CheckError(f"no check is named {name!r}")
    check = checks[name]
    if not isinstance(args, dict):
        raise CheckError(f"{name}: the arguments are not an object")
    wrong = sorted(set(args) - set(check.args)) + sorted(set(check.args) - set(args) - set(check.optional))
    bad = sorted(arg for arg, value in args.items() if arg in check.args and not check.args[arg](value))
    if wrong or bad:
        raise CheckError(f"{name}: arguments {wrong} are unknown or missing, and {bad} are not of their shape")
    return check


def decide(name, bundle, args, checks=None):
    """{"check", "outcome", "reason", "inferred"} of the check `name` on `bundle` with `args`: `inferred` is True
    when it is undecidable because evidence it reads is inferred."""
    check, inferred = validate(name, args, checks), False
    try:
        outcome, reason = check.decide(bundle, **args)
    except Undecidable as error:
        outcome, reason, inferred = "undecidable", str(error), isinstance(error, Inferred)
    except Exception as error:  # a check that breaks decides nothing, and the round stops
        raise CheckError(f"{name}: the check failed to run: {type(error).__name__}: {error}") from None
    if outcome not in OUTCOMES or not isinstance(reason, str) or not reason:
        raise CheckError(f"{name}: gave {outcome!r} with reason {reason!r}, not an outcome with a reason")
    return {"check": name, "outcome": outcome, "reason": reason, "inferred": inferred}


def keys(name, folder=KEYS):
    """The answer keys of the check `name`: {key name: key data}, from `folder/<name>/*.json`."""
    found = {}
    for path in sorted((Path(folder) / name).glob("*.json")):
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or not {"args", "outcome"} <= set(data) <= KEY_FIELDS \
                or data["outcome"] not in OUTCOMES:
            raise CheckError(f"{path}: an answer key holds args and outcome, and only {sorted(KEY_FIELDS)}")
        found[path.stem] = data
    return found


def prove(name, checks=None, folder=KEYS):
    """The answer keys of `name` it gets wrong, as {key: what it gave}. CheckError unless the check has a key that
    must pass and one that must fail."""
    given = keys(name, folder)
    if not {"pass", "fail"} <= {data["outcome"] for data in given.values()}:
        raise CheckError(f"{name}: needs an answer key that must pass and one that must fail")
    wrong = {}
    for key, data in given.items():
        verdict = decide(name, Bundle.key(data), data["args"], checks)
        if verdict["outcome"] != data["outcome"]:
            wrong[key] = verdict
    return wrong
