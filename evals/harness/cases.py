"""Eval cases: one folder per case, `evals/skills/NAME/cases/<case>/`, holding `world/` and `case.json`.

`world/` is the whole project the agent works in, written without the skill. `case.json` says what the run is
given on top of it. This module reads `case.json` and checks it against one schema, `SCHEMA`: every field the
file may hold, each with the one shape it may take. A field that is not in the schema, or does not have its
shape, is refused with the reason.

case.json fields:

- `prompt` (text, required) and `kind` (`trigger` or `task`, required).
- `should_trigger` (true or false) and `split` (`train` or `test`): required in trigger cases, refused in task
  cases.
- `skill_path`: where the skill goes in the with-skill arm, default `skills/NAME`.
- `index`: the index file the world uses and how a row is written: `{"file": "AGENTS.md", "after": "| Skill |
  Path | Use when |", "row": "| {name} | [{path}]({path}) | {description} |"}`. `{path}` is the skill's SKILL.md.
  Required in trigger cases, which install the full skill set with its index, as in real use.
- `siblings`: names of other skills installed in both arms.
- `tools`: commands the case needs on the host, such as `go`; the tools probe records their versions.
- `expectations`: what the run must show: each a text, or an object holding only its `text`. The checks of doc 11
  (Scoring) add their fields to this shape when they are built.
- `commits`: git history to build, `[{"message": "...", "paths": ["a.txt"]}]`, with fixed authors and dates.
- `copies`: documents copied from this repository, `[{"world": "AGENTS.md", "source": "AGENTS.md",
  "source_sha256": "..."}]`. `source_sha256` is the source's hash when it was copied. A source is never under
  `skills/` or `evals/`: a skill's text or the measuring kit is not project text.
- `allow_words`: test-tell words a place may hold, keyed by a world path, `<prompt>` or `<commit N>` (N counts
  the commits from 1): `{"docs/testing.md": ["fixture"], "<prompt>": ["eval"]}`.

Every path is relative and inside the world: parts of ASCII letters, digits and `. _ + @ -`, joined by `/`, and
never `.`, `..` or `.git`. Every shape is a pattern of what is allowed.
"""

import hashlib
import json
import re
import string
from pathlib import Path

import manifest

REPO = Path(__file__).resolve().parents[2]
KINDS = ("trigger", "task")
SPLITS = ("train", "test")
PROMPT_KEY = "<prompt>"
SKILL_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
SHA256 = re.compile(r"[0-9a-f]{64}")
# One part of a path: ASCII letters, digits and . _ + @ -, never `.`, `..` or `.git`.
PATH_PART = re.compile(r"[A-Za-z0-9._+@-]+")
NOT_PARTS = (".", "..", ".git")
COMMAND = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
ROW_FIELDS = ("name", "path", "description")
NOT_PROJECT_TEXT = ("skills", "evals")


class CaseError(ValueError):
    """A case that cannot be built or run, with the reason."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


# The shapes a value may take. Each returns True only for a value of exactly that shape.

def is_text(value):
    return isinstance(value, str) and value.strip() != ""


def is_name(value):
    return isinstance(value, str) and SKILL_NAME.fullmatch(value) is not None


def is_path(value):
    """A relative path inside the world: parts of PATH_PART joined by `/`, with no `.`, `..` or `.git` part."""
    return isinstance(value, str) and all(PATH_PART.fullmatch(part) and part not in NOT_PARTS
                                          for part in value.split("/"))


def is_command(value):
    return isinstance(value, str) and COMMAND.fullmatch(value) is not None


def is_source(value):
    return is_path(value) and value.split("/")[0] not in NOT_PROJECT_TEXT


def is_row(value):
    """A row whose every replacement field is exactly `{name}`, `{path}` or `{description}`: no index,
    attribute, conversion or format spec."""
    if not is_text(value):
        return False
    try:
        fields = list(string.Formatter().parse(value))
    except ValueError:
        return False
    return all(field is None or (field in ROW_FIELDS and not spec and conversion is None)
               for _, field, spec, conversion in fields)


def is_expectation(value):
    """A text, or an object holding only a text. Later parts add the fields of checks."""
    return is_text(value) or record(text=is_text)(value)


def list_of(shape):
    return lambda value: isinstance(value, list) and all(shape(item) for item in value)


def record(**fields):
    """An object with exactly these fields, each of its shape."""
    return lambda value: (isinstance(value, dict) and set(value) == set(fields)
                          and all(shape(value[key]) for key, shape in fields.items()))


def is_allow_words(value):
    return isinstance(value, dict) and all(isinstance(key, str) and list_of(is_text)(words)
                                           for key, words in value.items())


SCHEMA = {
    "prompt": (is_text, "non-empty text"),
    "kind": (lambda v: v in KINDS, f"one of {KINDS}"),
    "should_trigger": (lambda v: isinstance(v, bool), "true or false"),
    "split": (lambda v: v in SPLITS, f"one of {SPLITS}"),
    "skill_path": (is_path, "a relative path inside the world (ASCII letters, digits and . _ + @ - in each part)"),
    "index": (record(file=is_path, after=is_text, row=is_row),
              "{file, after, row}: a path in the world, the header line, and a row using only {name}, {path} "
              "and {description}"),
    "siblings": (list_of(is_name), "a list of skill names (lower-case letters, digits and hyphens)"),
    "tools": (list_of(is_command), "a list of command names (letters, digits and . _ + -)"),
    "expectations": (list_of(is_expectation), "a list of texts, or of objects holding only a non-empty text"),
    "commits": (list_of(record(message=is_text, paths=list_of(is_path))),
                "a list of {message, paths}: non-empty text and a list of paths in the world"),
    "copies": (list_of(record(world=is_path, source=is_source, source_sha256=lambda v: isinstance(v, str)
                              and SHA256.fullmatch(v) is not None)),
               "a list of {world, source, source_sha256}: two paths, the source outside skills/ and evals/, "
               "and its 64-character lower-case hex sha256"),
    "allow_words": (is_allow_words, "an object mapping a place to a list of words"),
}
REQUIRED = {"task": ("prompt", "kind"), "trigger": ("prompt", "kind", "should_trigger", "split", "index")}
TRIGGER_ONLY = ("should_trigger", "split")
DEFAULTS = {"siblings": [], "tools": [], "expectations": [], "commits": [], "copies": [], "allow_words": {}}


def check(data, case_id, skill=None):
    """Return the case data with defaults filled in, or raise CaseError naming every problem."""
    if not isinstance(data, dict):
        raise CaseError(f"{case_id}: case.json must be an object")
    problems = [f"unknown field {key!r}" for key in sorted(set(data) - set(SCHEMA))]
    for key, (shape, wanted) in SCHEMA.items():
        if key in data and not shape(data[key]):
            problems.append(f"{key} must be {wanted}")
    kind = data.get("kind") if data.get("kind") in KINDS else None
    for key in REQUIRED.get(kind, ("prompt", "kind")):
        if key not in data:
            problems.append(f"a {kind or 'case'} needs {key}")
    if kind == "task":
        problems += [f"{key} is only for trigger cases" for key in TRIGGER_ONLY if key in data]
    siblings = data.get("siblings") if isinstance(data.get("siblings"), list) else []
    if len(set(map(str, siblings))) != len(siblings):
        problems.append("siblings must not repeat")
    if skill is not None and skill in siblings:
        problems.append(f"the skill under test, {skill}, cannot also be a sibling")
    problems += _allow_keys(data)
    if problems:
        raise CaseError(f"{case_id}: " + "; ".join(problems))
    return {**DEFAULTS, **data}


def _allow_keys(data):
    """Each allow_words key names a place the agent sees: a world path, the prompt or a declared commit."""
    allow, commits = data.get("allow_words"), data.get("commits")
    if not isinstance(allow, dict):
        return []
    count = len(commits) if isinstance(commits, list) else 0
    places = {PROMPT_KEY} | {commit_key(n) for n in range(1, count + 1)}
    return [f"allow_words key {key!r} must be a world path, {PROMPT_KEY} or <commit N> for a declared commit"
            for key in allow if not (key in places or is_path(key))]


def commit_key(number):
    return f"<commit {number}>"


class Case:
    """One eval case, read and checked. `skill` is the skill's name, `folder` the case folder."""

    def __init__(self, folder, skill):
        self.folder = Path(folder)
        self.skill = skill
        self.id = self.folder.name
        self.world = self.folder / "world"
        if not is_name(skill):
            raise CaseError(f"{self.id}: {skill!r} is not a skill name")
        path = self.folder / "case.json"
        if not path.is_file():
            raise CaseError(f"{self.id}: no case.json")
        if not self.world.is_dir() or self.world.is_symlink():
            raise CaseError(f"{self.id}: no world/ folder")
        try:
            data = json.loads(path.read_bytes().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CaseError(f"{self.id}: case.json is not UTF-8 JSON: {error}") from None
        self.data = check(data, self.id, skill)
        try:
            world = {f"world/{k}": v for k, v in manifest.manifest(self.world).items()}
        except manifest.Unreadable as error:
            raise CaseError(f"{self.id}: {error}") from None
        self.sha256 = manifest.digest({"case.json": "file " + sha256_file(path), **world})

    def __getattr__(self, name):
        if name in SCHEMA:
            return self.data.get(name)
        raise AttributeError(name)

    @property
    def skill_rel(self):
        return self.data.get("skill_path") or f"skills/{self.skill}"


def load_cases(skill, root=None):
    """Every case of a skill, sorted by id."""
    root = Path(root) if root else REPO / "evals" / "skills" / skill / "cases"
    if not root.is_dir():
        raise CaseError(f"{skill}: no cases folder at {root}")
    return [Case(folder, skill) for folder in sorted(root.iterdir()) if folder.is_dir()]
