"""World lint: reject a case whose world or prompt is unsound, before any run (doc 11, World lint).

Every rule reads one list, `visible`: each place the without-skill run can see, read from the built arm on disk.
A place is a world entry (its path, and its bytes or link target), the prompt, a declared commit message, or the
index rows the builder wrote. No entry is skipped: text in any encoding, at any size, is read. Each place has an
origin, which decides the rules it answers to:

- `world`: what the case author wrote, including the prompt and commit messages;
- `copy`: a document copied from this repository, still byte for byte its recorded source;
- `installed`: sibling skills and their index rows, which are real project content.
"""

import re
import tempfile
from pathlib import Path

import manifest
import world
from cases import PROMPT_KEY, REPO, CaseError, commit_key, load_cases
from skills import skill_files

FINGERPRINT_RUN = 8
EXPECTATION_RUN = 6
# Words that tell an agent it is being tested (doc 11). A place may allow some through `allow_words`.
TELLS = ("eval", "evals", "evaluation", "evaluated", "fixture", "fixtures", "grader", "graders", "grading",
         "graded", "benchmark", "benchmarks", "rubric", "golden", "test harness", "harness run")
# The names of the measuring kit's own files and folders, which never belong in a world.
KIT_NAMES = ("case.json", "tasks.json", "triggers.json", "grading.json", "expectations.json", "verdict.json")
KIT_FOLDERS = ("evals", "cases", "goldens", "results")
INDEX_ROWS = "<index rows>"


class Place:
    """One thing the run can see: where it is, its text, and its origin."""

    def __init__(self, key, text, origin):
        self.key, self.text, self.origin = key, text, origin
        self.words = " ".join(words(text))


def words(text):
    """The words of `text`: lower-case runs of letters and digits. Names, paths and phrases match on these, so
    `haiku-writer`, `Haiku_Writer` and `haiku writer` are the same words."""
    return re.findall(r"[a-z0-9]+", text.lower())


def runs(text, size):
    found = words(text)
    return {" ".join(found[i:i + size]) for i in range(len(found) - size + 1)}


def contains(place, phrase):
    wanted = " ".join(words(phrase))
    return bool(wanted) and f" {wanted} " in f" {place.words} "


def decode(data):
    """Bytes as text, never refused: UTF-8 when it decodes, otherwise one character per byte, so ASCII stays
    readable."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _hash(entry):
    """The sha256 of a regular file's entry, or None for anything else."""
    return entry.split(" ")[1] if manifest.is_file(entry) else None


def copies(case):
    """The world paths that are still byte for byte the copy their case entry records."""
    entries = manifest.manifest(case.world)
    return {c["world"] for c in case.copies if _hash(entries.get(c["world"], "")) == c["source_sha256"]}


def visible(case, arm):
    """Every place the without-skill run of `case` can see, from the built arm `arm`.

    The arm must be exactly what the case says, so the index file is read as the world wrote it plus the rows the
    builder added, and every other entry is read from the arm.
    """
    want, _ = world.expected(case, arm.installs)
    files, _ = arm.read()
    if files != want:
        raise CaseError(f"{case.id}: the built arm is not what the case says")
    targets = [target for install in arm.installs for target in install.targets]
    copied = copies(case)
    index = case.index["file"] if case.index else None
    places = [Place(PROMPT_KEY, case.prompt, "world")]
    places += [Place(commit_key(n), c["message"], "world") for n, c in enumerate(case.commits, 1)]
    for path, entry in sorted(files.items()):
        origin = ("installed" if any(path == t or path.startswith(t + "/") for t in targets)
                  else "copy" if path in copied else "world")
        if path == index:
            body = decode((case.world / path).read_bytes())
        elif manifest.kind(entry) == "file":
            body = decode((arm.path / path).read_bytes())
        elif manifest.kind(entry) == "link":
            body = entry[len("link "):]
        else:
            body = ""
        places.append(Place(path, f"{path}\n{body}", origin))
    rows = [install.row for install in arm.installs if install.row is not None]
    if rows:
        places.append(Place(INDEX_ROWS, "\n".join(rows), "installed"))
    return places


def fingerprint(skill_dir, name, shared):
    """Every 8-word run of the skill's own text: its runs, minus those in the `shared` texts."""
    files, _ = skill_files(skill_dir, name)
    own = set().union(*(runs(decode(data), FINGERPRINT_RUN) for data in files.values()))
    return own - set().union(set(), *(runs(text, FINGERPRINT_RUN) for text in shared))


def upstream_texts(folder):
    """The text of every file of the skill's recorded upstream source, or none when it is not recorded."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return [decode((folder / path).read_bytes()) for path, entry in sorted(manifest.manifest(folder).items())
            if manifest.kind(entry) == "file"]


def lint(case, arm, skill_dir, upstream=(), repo=REPO):
    """Every problem with `case`, given its built without-skill arm. An empty list means it passes."""
    places = visible(case, arm)
    problems = []
    names = [case.skill] + ([case.skill_rel] if case.skill_rel != f"skills/{case.skill}" else [])
    shared = [p.text for p in places if p.origin == "copy" or p.key == PROMPT_KEY] + list(upstream)
    marks = fingerprint(skill_dir, case.skill, shared)
    expected = set().union(set(), *(runs(e if isinstance(e, str) else e["text"], EXPECTATION_RUN)
                                    for e in case.expectations))
    allow = {key: {" ".join(words(w)) for w in allowed} for key, allowed in case.allow_words.items()}
    for place in places:
        problems += [f"{place.key}: names the skill ({name!r})" for name in names if contains(place, name)]
        hits = sorted(marks & runs(place.text, FINGERPRINT_RUN)) if place.origin != "copy" else []
        if hits:
            problems.append(f"{place.key}: holds {len(hits)} run(s) of the skill's own text, such as {hits[0]!r}")
        if place.origin != "world":
            continue
        problems += [f"{place.key}: test-tell word {tell!r}" for tell in TELLS
                     if tell not in allow.get(place.key, set()) and contains(place, tell)]
        if expected & runs(place.text, EXPECTATION_RUN):
            problems.append(f"{place.key}: holds expectation text")
        parts = place.key.split("/")
        if not place.key.startswith("<") and (parts[-1] in KIT_NAMES or any(p in KIT_FOLDERS for p in parts)):
            problems.append(f"{place.key}: an eval file inside the world")
    problems += _copies(case, repo)
    return [f"{case.id}: {p}" for p in problems]


def _copies(case, repo):
    problems, copied = [], copies(case)
    for copy in case.copies:
        try:
            source = _hash(manifest.entry(Path(repo) / copy["source"]))
        except manifest.Unreadable:
            source = None
        if copy["world"] not in copied:
            problems.append(f"copy {copy['world']}: not in the world as the regular file its source_sha256 names")
        elif source is None:
            problems.append(f"copy {copy['world']}: source {copy['source']} is not a regular file")
        elif source != copy["source_sha256"]:
            problems.append(f"copy {copy['world']}: {copy['source']} changed since it was copied; review the copy "
                            "and record the new source_sha256")
    return problems


def lint_skill(skill, adapter, cases_root=None, skills_root=None, repo=REPO):
    """Lint every case of a skill for the host of `adapter`. Returns the problems; none means every case may run."""
    skills_root = Path(skills_root) if skills_root else repo / "skills"
    upstream = upstream_texts(repo / "evals" / "skills" / skill / "upstream")
    problems = []
    for case in load_cases(skill, cases_root):
        with tempfile.TemporaryDirectory(prefix="hw-lint-") as folder:
            try:
                arm = world.build(case, adapter, Path(folder) / "arm", skills_root)
                problems += lint(case, arm, skills_root / skill, upstream, repo)
            except CaseError as error:
                problems.append(str(error))
    return problems
