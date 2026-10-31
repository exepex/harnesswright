"""Eval cases: one folder per case, `evals/skills/NAME/cases/<case>/`, holding `world/` and `case.json`.

`world/` is the whole project the agent works in, written without the skill. `case.json` says what the run is
given on top of it. This module reads and checks `case.json`; `world.py` builds the arms from it.

case.json fields:

- `prompt` (text, required) and `kind` (`trigger` or `task`, required).
- `skill_path`: where the skill goes in the with-skill arm, default `skills/NAME`.
- `index`: the index file the world uses and how a row is written: `{"file": "AGENTS.md", "after": "| Skill |
  Path | Use when |", "row": "| {name} | [{path}]({path}) | {description} |"}`. `{path}` is the skill's SKILL.md.
- `siblings`: other skills installed in both arms, as in real use (trigger worlds install the full skill set).
- `tools`: commands the case needs on the host, such as `go`; the tools probe records their versions.
- `expectations`: what the run must show, a list. Checks and graders decide them (doc 11, Scoring).
- `should_trigger` (trigger cases, required) and `split` (`train` or `test`, trigger cases, required).
- `commits`: git history to build, `[{"message": "...", "paths": ["a.txt"]}]`, with fixed authors and dates.
- `copies`: documents copied from this repository, `[{"world": "AGENTS.md", "source": "AGENTS.md",
  "source_sha256": "..."}]`. `source_sha256` is the source's hash when it was copied. The lint fails when the
  world's copy differs from it, or when the source has changed since, so the copy is reviewed again.
- `allow_words`: test-tell words a file may hold, `{"docs/testing.md": ["fixture"], "<prompt>": ["eval"]}`.
"""

import hashlib
import json
from pathlib import Path

import manifest

REPO = Path(__file__).resolve().parents[2]
KINDS = ("trigger", "task")
SPLITS = ("train", "test")
FIELDS = {"prompt", "kind", "skill_path", "index", "siblings", "tools", "expectations", "should_trigger",
          "split", "commits", "copies", "allow_words"}
PROMPT_KEY = "<prompt>"


class CaseError(ValueError):
    """A case that cannot be built or run, with the reason."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


class Case:
    """One eval case, read and checked. `skill` is the skill's name, `folder` the case folder."""

    def __init__(self, folder, skill):
        self.folder = Path(folder)
        self.skill = skill
        self.id = self.folder.name
        self.world = self.folder / "world"
        path = self.folder / "case.json"
        if not path.is_file():
            raise CaseError(f"{self.id}: no case.json")
        if not self.world.is_dir():
            raise CaseError(f"{self.id}: no world/ folder")
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            raise CaseError(f"{self.id}: case.json is not JSON: {error}") from None
        self.data = check(data, self.id)
        world = {f"world/{k}": v for k, v in manifest.manifest(self.world).items()}
        self.sha256 = manifest.digest({"case.json": "file " + sha256_file(path), **world})

    def __getattr__(self, name):
        if name in FIELDS:
            return self.data.get(name)
        raise AttributeError(name)

    @property
    def skill_rel(self):
        return self.data.get("skill_path") or f"skills/{self.skill}"


def check(data, case_id):
    """Return the case data with defaults filled in, or raise CaseError naming every problem."""
    problems = []
    if not isinstance(data, dict):
        raise CaseError(f"{case_id}: case.json must be an object")
    unknown = sorted(set(data) - FIELDS)
    if unknown:
        problems.append(f"unknown fields {unknown}")
    if not isinstance(data.get("prompt"), str) or not data.get("prompt", "").strip():
        problems.append("prompt must be non-empty text")
    if data.get("kind") not in KINDS:
        problems.append(f"kind must be one of {KINDS}")
    if data.get("kind") == "trigger":
        if not isinstance(data.get("should_trigger"), bool):
            problems.append("a trigger case needs should_trigger true or false")
        if data.get("split") not in SPLITS:
            problems.append(f"a trigger case needs split, one of {SPLITS}")
    if "skill_path" in data and not _relative(data["skill_path"]):
        problems.append("skill_path must be a relative path inside the world")
    index = data.get("index")
    if index is not None:
        if not isinstance(index, dict) or not {"file", "after", "row"} <= set(index):
            problems.append("index needs file, after and row")
        elif not _relative(index["file"]):
            problems.append("index.file must be a relative path inside the world")
    for key in ("siblings", "tools", "expectations"):
        if key in data and not (isinstance(data[key], list) and all(isinstance(v, (str, dict)) for v in data[key])):
            problems.append(f"{key} must be a list")
    for commit in data.get("commits") or []:
        if not (isinstance(commit, dict) and isinstance(commit.get("message"), str)
                and isinstance(commit.get("paths"), list)):
            problems.append("each commit needs a message and a list of paths")
    for copy in data.get("copies") or []:
        if not (isinstance(copy, dict) and {"world", "source", "source_sha256"} <= set(copy)):
            problems.append("each copy needs world, source and source_sha256")
    allow = data.get("allow_words") or {}
    if not (isinstance(allow, dict) and all(isinstance(v, list) for v in allow.values())):
        problems.append("allow_words must map a path to a list of words")
    if problems:
        raise CaseError(f"{case_id}: " + "; ".join(problems))
    filled = dict(data)
    filled.setdefault("siblings", [])
    filled.setdefault("tools", [])
    filled.setdefault("expectations", [])
    filled.setdefault("commits", [])
    filled.setdefault("copies", [])
    filled.setdefault("allow_words", {})
    return filled


def _relative(path):
    return isinstance(path, str) and path and not Path(path).is_absolute() and ".." not in Path(path).parts


def load_cases(skill, root=None):
    """Every case of a skill, sorted by id."""
    root = Path(root) if root else REPO / "evals" / "skills" / skill / "cases"
    if not root.is_dir():
        raise CaseError(f"{skill}: no cases folder at {root}")
    return [Case(folder, skill) for folder in sorted(root.iterdir()) if folder.is_dir()]


def skill_files(skill_dir):
    """The skill's files as {relative path: bytes}, and its name and description from the frontmatter."""
    skill_dir = Path(skill_dir)
    files = {p.relative_to(skill_dir).as_posix(): p.read_bytes()
             for p in sorted(skill_dir.rglob("*")) if p.is_file()}
    if "SKILL.md" not in files:
        raise CaseError(f"{skill_dir}: no SKILL.md")
    meta = frontmatter(files["SKILL.md"].decode())
    if not meta.get("name") or not meta.get("description"):
        raise CaseError(f"{skill_dir}: SKILL.md frontmatter needs name and description")
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
                meta[name] = json.loads(value) if value[0] == '"' else value[1:-1]
            else:
                meta[name] = value
    return meta


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
