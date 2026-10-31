"""Eval cases: one folder per case, `evals/skills/NAME/cases/<case>/`, holding `world/` and `case.json`.

`world/` is the whole project the agent works in, written without the skill. `case.json` says what the run is
given on top of it. This module reads `case.json` and checks it against one schema, `SCHEMA`: every field the
file may hold, each with the one shape it may take. A field that is not in the schema, or does not have its
shape, is refused with the reason. Nothing is checked by looking for known bad values.

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
- `expectations`: what the run must show: each a text, or an object whose `text` states it (doc 11, Scoring).
- `commits`: git history to build, `[{"message": "...", "paths": ["a.txt"]}]`, with fixed authors and dates.
- `copies`: documents copied from this repository, `[{"world": "AGENTS.md", "source": "AGENTS.md",
  "source_sha256": "..."}]`. `source_sha256` is the source's hash when it was copied. A source is never under
  `skills/` or `evals/`: a skill's text or the measuring kit is not project text.
- `allow_words`: test-tell words a place may hold, keyed by a world path, `<prompt>` or `<commit N>` (N counts
  the commits from 1): `{"docs/testing.md": ["fixture"], "<prompt>": ["eval"]}`. A key that starts with `<` is
  always a place, never a path.

Every path is relative, inside the world, written with `/`, and never names `.git`.
"""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

import manifest

REPO = Path(__file__).resolve().parents[2]
KINDS = ("trigger", "task")
SPLITS = ("train", "test")
PROMPT_KEY = "<prompt>"
SKILL_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
SHA256 = re.compile(r"[0-9a-f]{64}")
NOT_PROJECT_TEXT = ("skills", "evals")
ROW_KEYS = {"name": "n", "path": "p", "description": "d"}


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
    """A relative path inside the world, written with `/`, with no `.`, `..` or `.git` part."""
    if not (isinstance(value, str) and value and "\\" not in value and "\0" not in value):
        return False
    parts = value.split("/")
    return all(part not in ("", ".", "..", ".git") for part in parts) and not PurePosixPath(value).is_absolute()


def is_source(value):
    return is_path(value) and value.split("/")[0] not in NOT_PROJECT_TEXT


def is_row(value):
    if not is_text(value):
        return False
    try:
        value.format(**ROW_KEYS)
    except (KeyError, IndexError, ValueError, AttributeError):
        return False
    return True


def is_expectation(value):
    if isinstance(value, dict):
        return is_text(value.get("text"))
    return is_text(value)


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
    "skill_path": (is_path, "a relative path inside the world"),
    "index": (record(file=is_path, after=is_text, row=is_row),
              "{file, after, row}: a path in the world, the header line, and a row using only {name}, {path} "
              "and {description}"),
    "siblings": (list_of(is_name), "a list of skill names (lower-case letters, digits and hyphens)"),
    "tools": (list_of(is_text), "a list of command names"),
    "expectations": (list_of(is_expectation), "a list of texts, or of objects with a non-empty text"),
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
    kind = data.get("kind")
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
            for key in allow if not (key in places or (is_path(key) and not key.startswith("<")))]


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
        world = {f"world/{k}": v for k, v in manifest.manifest(self.world).items()}
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


def skill_files(skill_dir, name=None):
    """The skill's files as {relative path: bytes}, and its name and description from the frontmatter.

    The frontmatter name must be a skill name, and `name` when one is given: the name chooses where the host
    discovers the skill, so it must never be a path.
    """
    skill_dir = Path(skill_dir)
    files = {p.relative_to(skill_dir).as_posix(): p.read_bytes()
             for p in sorted(skill_dir.rglob("*")) if p.is_file() and not p.is_symlink()}
    if "SKILL.md" not in files:
        raise CaseError(f"{skill_dir}: no SKILL.md")
    meta = frontmatter(files["SKILL.md"].decode("utf-8", errors="replace"))
    if not meta.get("name") or not meta.get("description"):
        raise CaseError(f"{skill_dir}: SKILL.md frontmatter needs name and description")
    if not is_name(meta["name"]) or (name is not None and meta["name"] != name):
        wanted = repr(name) if name is not None else "a skill name"
        raise CaseError(f"{skill_dir}: frontmatter name {meta['name']!r} must be {wanted}")
    return files, meta


def frontmatter(text):
    """The top-level `key: value` pairs of a SKILL.md frontmatter block. A block scalar (`>` or `|`) is joined
    into one line, and a quoted value loses its quotes."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta, key = {}, None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if key and line[:1] in (" ", "\t"):
            meta[key] = f"{meta[key]} {line.strip()}".strip()
            continue
        key = None
        if line and not line[0].isspace() and ":" in line:
            name, value = (part.strip() for part in line.split(":", 1))
            if value in (">", "|", ">-", "|-", ">+", "|+"):
                meta[name], key = "", name
            elif len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                meta[name] = _unquote(value)
            else:
                meta[name] = value
    return meta


def _unquote(value):
    if value[0] == "'":
        return value[1:-1].replace("''", "'")
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value[1:-1]


def structure(world):
    """A `.git` folder, an absolute symlink or a symlink that points outside the world, in a written world.

    A copied absolute symlink still points at the source world, so writes through it would reach the case.
    """
    problems = []
    root = Path(world).resolve()
    for path in sorted(Path(world).rglob("*")):
        relative = path.relative_to(world).as_posix()
        if path.name == ".git":
            problems.append(f"{relative}: a .git folder; declare history as commits in case.json")
        if path.is_symlink():
            link = path.readlink()
            if link.is_absolute():
                problems.append(f"{relative}: an absolute symlink; use a relative one inside the world")
            elif not (path.parent / link).resolve().is_relative_to(root):
                problems.append(f"{relative}: a symlink that points outside the world")
    return problems
