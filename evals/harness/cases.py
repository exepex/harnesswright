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
- `expectations`: what the run must show (doc 11, Scoring). Each is `{"text", "source", "judged"}`, and `"check"`
  when a script can decide it:
  - `text`: what it says, in plain words.
  - `source`: where the rule comes from: `"format"`, the skill's own format, or `{"contract": {"path", "line",
    "quote"}}`, a rule a world document states, which the lint finds: `quote` starts on line `line` of `path`.
  - `judged`: what the graders read when no check decides it: `{"question", "pass", "fail", "examples": {"pass":
    [texts], "fail": [texts]}}`, a yes-or-no question, the rule for each answer and at least one example of each.
    Every expectation has one, since a check that cannot decide sends its expectation to the graders.
  - `check`: `{"name", "args"}`, a script check of `evals/checks/` and its arguments, which the lint checks against
    that check's own list.
- `commits`: git history to build, `[{"message": "...", "paths": ["a.txt"]}]`, with fixed authors and dates.
- `copies`: documents copied from this repository, `[{"world": "AGENTS.md", "source": "AGENTS.md",
  "source_sha256": "..."}]`. `source_sha256` is the source's hash when it was copied. A source is a file at the
  repository root, such as `AGENTS.md`: a project document. Every folder holds skill text, its sources, the
  measuring kit or harnesswright's own design and formats, which a project using a skill does not have.
- `situation`: in a task case only, the pressure it puts on the agent (doc 11, Pressure situations), one of
  `SITUATIONS`. A case of `check-cannot-run` runs with the skill only (`SKILL_ONLY`); every other runs in both arms.
- `internal_world`: in a case of an internal skill only, `{"remove": [paths], "jobs": [rows]}`, `jobs` optional:
  the world is the skill's internal world (`internal.py`, doc 12, Internal worlds) with `world/` copied on top,
  when the case has one, the `jobs` rows added to the Jobs table of `v2/roles.md`, its release rebuilt and checked,
  less the `remove` paths, each inside the kit's allow list. Without it, `world/` is the whole world, as before.
- `profile_version`: in a team skill's case whose profile names a release folder only, the version the arms'
  profiles state when the case tests a mismatch on purpose; without it each arm's states its release's (doc 12).
- `allow_words`: test-tell words a place may hold, keyed by a world path, `<prompt>` or `<commit N>` (N counts
  the commits from 1): `{"docs/testing.md": ["fixture"], "<prompt>": ["eval"]}`.

Every path is relative and inside the world: parts of ASCII letters, digits and `. _ + @ -`, joined by `/`, and
never `.`, `..` or `.git`. Every shape is a pattern of what is allowed.

Every task case also gets one expectation it does not write: the done question, `evals/grading/done.json`, source
`"done"`, appended last (`Case.expectations`). The graders answer whether the run says its work is done, and the
label counts a false done when it says so and a contract expectation failed. It is graded, calibrated by goldens
and fingerprinted like any other expectation, never decided by a check, and part of the case's hash.

Every task case of a skill that `evals/checks/skill-checks.json` lists also gets the stop pair, two checks it does
not write (`Case.reported`, `stoppair.py`): reported per arm, never counted or graded, and part of the case's hash.
"""

import hashlib
import json
import re
import string
import unicodedata
from pathlib import Path

import manifest

REPO = Path(__file__).resolve().parents[2]
DONE = REPO / "evals" / "grading" / "done.json"  # the done question every task case is asked
SITUATION_FILE = REPO / "evals" / "situations.json"  # the situations each skill's cases must cover
KIND_FILE = REPO / "evals" / "kinds.json"  # each skill's kind (doc 12, Skill kinds)
STOP_CHECKS = ("blocked_after_failed_check", "blocked_quotes_output")  # the stop pair's, which no case writes
OWN_CHECK_FILE = REPO / "evals" / "own-checks.json"  # the checks that run harnesswright's own (doc 12, Worlds by kind)
SKILL_KINDS = ("team", "internal")
KINDS = ("trigger", "task")
# The arms a case runs in. A grader must never learn its run's arm, so no world, prompt or page may hold these names.
ARMS = ("without_skill", "with_skill")
PREVIOUS = "previous_version"
SPLITS = ("train", "test")
PROMPT_KEY = "<prompt>"
SKILL_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
SHA256 = re.compile(r"[0-9a-f]{64}")
# One part of a path: ASCII letters, digits and . _ + @ -, never `.`, `..` or `.git`.
PATH_PART = re.compile(r"[A-Za-z0-9._+@-]+")
NOT_PARTS = (".", "..", ".git")
COMMAND = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
CHECK_NAME = re.compile(r"[a-z][a-z0-9_]*")
ROW_FIELDS = ("name", "path", "description")
# The pressure situations a task case may put on the agent (doc 11), and the one a plain agent cannot fail, since the
# check it forbids is the skill's own: it runs with the skill only, and counts in no pass rate, lift or false done.
SITUATIONS = ("missing-input", "untestable-input", "lower-the-bar", "check-cannot-run", "self-judge",
              "stale-evidence", "outside-text", "green-not-proven")
SKILL_ONLY = ("check-cannot-run",)


class CaseError(ValueError):
    """A case that cannot be built or run, with the reason."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


# The shapes a value may take. Each returns True only for a value of exactly that shape.

def is_plain(text):
    """True when `text` holds no control, surrogate, private or unassigned character other than tab, line feed and
    carriage return. Every text a run sees obeys this one rule: world files, the prompt, commit messages and rows."""
    return not any(unicodedata.category(c) in ("Cc", "Cs", "Co", "Cn") and c not in "\t\n\r" for c in text)


def is_text(value):
    return isinstance(value, str) and value.strip() != "" and is_plain(value)


def is_name(value):
    return isinstance(value, str) and SKILL_NAME.fullmatch(value) is not None


def is_path(value):
    """A relative path inside the world: parts of PATH_PART joined by `/`, with no `.`, `..` or `.git` part."""
    return isinstance(value, str) and all(PATH_PART.fullmatch(part) and part not in NOT_PARTS
                                          for part in value.split("/"))


def is_command(value):
    return isinstance(value, str) and COMMAND.fullmatch(value) is not None


def is_source(value):
    return is_path(value) and "/" not in value  # a file at the repository root, the only project text allowed


def is_row(value):
    """A row whose every replacement field is exactly `{name}`, `{path}` or `{description}`: no index,
    attribute, conversion or format spec. It is one line and holds `{name}` or `{path}`, so the row names its skill;
    the grader view removes the row the install adds (`view.py`)."""
    if not is_text(value) or value.splitlines() != [value]:
        return False
    try:
        fields = list(string.Formatter().parse(value))
    except ValueError:
        return False
    return all(field is None or (field in ROW_FIELDS and not spec and conversion is None)
               for _, field, spec, conversion in fields) and bool({"name", "path"} & {f[1] for f in fields})


def list_of(shape):
    return lambda value: isinstance(value, list) and all(shape(item) for item in value)


def record(**fields):
    """An object with exactly these fields, each of its shape."""
    return lambda value: (isinstance(value, dict) and set(value) == set(fields)
                          and all(shape(value[key]) for key, shape in fields.items()))


def is_job_row(value):
    """One row of a Markdown table, on one line, as the Jobs table of `v2/roles.md` holds them."""
    return isinstance(value, str) and "\n" not in value and value.startswith("| ") and value.endswith(" |")


def is_line(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def some(shape):
    return lambda value: list_of(shape)(value) and bool(value)


# Where an expectation's rule comes from, and how it is decided: the one shape of an expectation.
CONTRACT = record(contract=record(path=is_path, line=is_line, quote=is_text))
EXPECTATION = {"text": is_text, "source": lambda v: v == "format" or CONTRACT(v),
               "judged": record(question=is_text, **{"pass": is_text, "fail": is_text},
                                examples=record(**{"pass": some(is_text), "fail": some(is_text)}))}
CHECK = record(name=lambda v: isinstance(v, str) and CHECK_NAME.fullmatch(v) is not None,
               args=lambda v: isinstance(v, dict))


def is_expectation(value):
    """{text, source, judged}, and a check when a script can decide it, each of its shape."""
    return (isinstance(value, dict) and set(EXPECTATION) <= set(value) <= set(EXPECTATION) | {"check"}
            and all(shape(value[key]) for key, shape in EXPECTATION.items())
            and ("check" not in value or CHECK(value["check"])))


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
    "expectations": (list_of(is_expectation),
                     "a list of {text, source, judged} and an optional check: source \"format\" or {contract: "
                     "{path, line, quote}}, judged {question, pass, fail, examples: {pass, fail}}, check {name, args}"),
    "commits": (list_of(record(message=is_text, paths=list_of(is_path))),
                "a list of {message, paths}: non-empty text and a list of paths in the world"),
    "copies": (list_of(record(world=is_path, source=is_source, source_sha256=lambda v: isinstance(v, str)
                              and SHA256.fullmatch(v) is not None)),
               "a list of {world, source, source_sha256}: two paths, the source a file at the repository root, "
               "and its 64-character lower-case hex sha256"),
    "allow_words": (is_allow_words, "an object mapping a place to a list of words"),
    "situation": (lambda v: v in SITUATIONS, f"one of {SITUATIONS}"),
    "profile_version": (lambda v: isinstance(v, str) and re.fullmatch(r"\d+\.\d+\.\d+", v) is not None,
                        "a version of three numbers, such as 0.7.1"),
    "internal_world": (lambda v: isinstance(v, dict) and "remove" in v and set(v) <= {"remove", "jobs"}
                       and list_of(is_path)(v["remove"]) and list_of(is_job_row)(v.get("jobs", [])),
                       "{remove: [paths], jobs: [rows]}: paths of the internal world, rows of its Jobs table"),
}
REQUIRED = {"task": ("prompt", "kind"), "trigger": ("prompt", "kind", "should_trigger", "split", "index")}
TRIGGER_ONLY = ("should_trigger", "split")
TASK_ONLY = ("situation",)
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
    elif kind == "trigger":
        problems += [f"{key} is only for task cases" for key in TASK_ONLY if key in data]
    siblings = data.get("siblings") if isinstance(data.get("siblings"), list) else []
    if len(set(map(str, siblings))) != len(siblings):
        problems.append("siblings must not repeat")
    if skill is not None and skill in siblings:
        problems.append(f"the skill under test, {skill}, cannot also be a sibling")
    problems += _allow_keys(data)
    listed = data.get("expectations") if isinstance(data.get("expectations"), list) else []
    problems += [f"expectation {n}: {e['check']['name']} is the stop pair's, which the harness adds (stoppair.py)"
                 for n, e in enumerate(listed, 1) if isinstance(e, dict) and isinstance(e.get("check"), dict)
                 and e["check"].get("name") in STOP_CHECKS]
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
        try:
            data = json.loads(path.read_bytes().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CaseError(f"{self.id}: case.json is not UTF-8 JSON: {error}") from None
        self.data = check(data, self.id, skill)
        bare = self.data.get("internal_world") is not None and not (self.world.exists() or self.world.is_symlink())
        if not bare and (not self.world.is_dir() or self.world.is_symlink()):
            raise CaseError(f"{self.id}: no world/ folder")
        hashed, self.reported = {}, []
        if self.data["kind"] == "task":
            import stoppair  # here, as it reads this module's shapes
            self.reported = stoppair.stop(skill) if skill in stoppair.skill_checks() else []
            self.data["expectations"] = [*self.data.get("expectations", []), done()]
            hashed = {"done.json": "file " + sha256_file(DONE)}
            if self.reported:
                hashed.update({"stop.json": "file " + sha256_file(stoppair.STOP),
                               "skill-checks.json": "file " + sha256_file(stoppair.SKILL_CHECKS)})
        try:
            self.world_files = {} if bare else manifest.manifest(self.world)  # {path: entry} of the case's world/
        except manifest.Unreadable as error:
            raise CaseError(f"{self.id}: {error}") from None
        world = {f"world/{k}": v for k, v in self.world_files.items()}
        self.sha256 = manifest.digest({"case.json": "file " + sha256_file(path), **world, **hashed})

    def __getattr__(self, name):
        if name in SCHEMA:
            return self.data.get(name)
        raise AttributeError(name)

    @property
    def skill_rel(self):
        return self.data.get("skill_path") or f"skills/{self.skill}"


def done(path=DONE):
    """The done question as an expectation: of an expectation's shape, with source `"done"` and no check."""
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaseError(f"{path.name}: {error}") from None
    if not (isinstance(data, dict) and data.get("source") == "done" and "check" not in data
            and is_expectation({**data, "source": "format"})):
        raise CaseError(f"{path.name}: the done question is {{text, source: \"done\", judged}} and nothing else")
    return data


def situations(path=SITUATION_FILE):
    """{skill: [situations that apply to it]} from the situation file, a kit part the judges approve: for each skill,
    `applies`, the situations its cases must cover, and `left_out`, each other situation with the reason a judge
    accepted. Every situation of `SITUATIONS` is in exactly one of the two, so none is left out unseen. With no file,
    no skill is listed, so every label stays `incomplete`."""
    if not Path(path).exists():
        return {}
    try:
        data = json.loads(Path(path).read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaseError(f"{Path(path).name}: {error}") from None
    if not isinstance(data, dict):
        raise CaseError(f"{Path(path).name}: must be an object of skills")
    found = {}
    for skill, entry in sorted(data.items()):
        shaped = record(applies=list_of(lambda v: v in SITUATIONS), left_out=lambda v: isinstance(v, dict) and all(
            is_text(reason) for reason in v.values()))(entry)
        if not (is_name(skill) and shaped and sorted([*entry["applies"], *entry["left_out"]]) == sorted(SITUATIONS)):
            raise CaseError(f"{Path(path).name}: {skill} must give {{applies: [situations], left_out: {{situation: "
                            f"reason}}}}, with each of {SITUATIONS} in exactly one")
        found[skill] = sorted(entry["applies"])
    return found


def kinds(path=KIND_FILE):
    """{skill: kind} from the kind file, a kit part the judges approve: the one reader of a skill's kind (doc 12,
    Skill kinds), each `team` or `internal`. A plan cannot set one. With no file, no skill has a kind, so every
    label stays `incomplete`."""
    if not Path(path).exists():
        return {}
    try:
        data = json.loads(Path(path).read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaseError(f"{Path(path).name}: {error}") from None
    if not isinstance(data, dict) or not all(is_name(skill) and kind in SKILL_KINDS for skill, kind in data.items()):
        raise CaseError(f"{Path(path).name}: must be an object of skills, each {' or '.join(SKILL_KINDS)}")
    return dict(sorted(data.items()))


def own_checks(path=OWN_CHECK_FILE):
    """The names of the script checks of `evals/checks/` that run harnesswright's own checks, from a kit part: the
    one list of them. An internal skill's task case counts only with a contract expectation one of them checks
    (`verdicts.decide`). With no file, no check counts."""
    if not Path(path).exists():
        return []
    try:
        data = json.loads(Path(path).read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaseError(f"{Path(path).name}: {error}") from None
    if not isinstance(data, list) or not all(isinstance(name, str) and CHECK_NAME.fullmatch(name) for name in data):
        raise CaseError(f"{Path(path).name}: must be a list of check names")
    return sorted(set(data))


def load_cases(skill, root=None):
    """Every case of a skill, sorted by id."""
    root = Path(root) if root else REPO / "evals" / "skills" / skill / "cases"
    if not root.is_dir():
        raise CaseError(f"{skill}: no cases folder at {root}")
    return [Case(folder, skill) for folder in sorted(root.iterdir()) if folder.is_dir()]
