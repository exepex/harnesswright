"""World lint: reject a case whose world or prompt is unsound, before any run (doc 11, World lint).

Every rule reads one list, `visible`: each place the without-skill run can see, read from the built arm once the
arm is proved to be what the case says. A place is a world entry (its path, and its text or link target), the
prompt, a commit message, the index row the case writes, or the index rows of installed siblings.

Each place has an author. `case` places are everything the case author controls, copies included. `harness`
places are installed sibling skills and their index rows: real project content, checked only for the skill.

What the lint reads is what an agent reads: every world file must be UTF-8 text with no control character other
than tab, line feed and carriage return. A file in any other form, such as UTF-16, an archive or a binary, is
refused rather than guessed at. Text is matched after Unicode compatibility folding, with format characters such
as soft hyphens removed, so look-alike spellings match too.
"""

import re
import tempfile
import unicodedata
from pathlib import Path

import manifest
import world
from cases import PROMPT_KEY, REPO, CaseError, commit_key, load_cases
from skills import skill_files

RUN = 8
EXPECTATION_RUN = 6
SHORTEST = 3
# Tell stems (doc 11): a word that starts with one tells an agent it is being tested. `allow_words` lets a place
# hold the words it names.
TELLS = ("eval", "fixture", "grader", "grading", "graded", "benchmark", "rubric", "golden", "test harness",
         "harness run", "ground truth", "expected output")
INDEX_ROW = "<index row>"
SIBLING_ROWS = "<sibling rows>"


class Place:
    """One thing the run can see: where it is, its text (None when the file is not plain text), and its author."""

    def __init__(self, key, text, author):
        self.key, self.text, self.author = key, text, author
        self.words = " ".join(words(text or ""))


def words(text):
    """The words of `text` after compatibility folding, with format characters removed: lower-case runs of
    letters and digits in any script. `haiku-writer`, `Haiku_Writer` and `haiku writer` are the same words."""
    folded = "".join(c for c in unicodedata.normalize("NFKC", text) if unicodedata.category(c) != "Cf")
    # ASCII letters and digits form words of their own, so a name written flush against text in another script,
    # as in Chinese or Japanese prose, is still a word.
    return re.findall(r"[a-z0-9]+|[^\W_a-z0-9]+", folded.casefold())


def runs(text, size):
    found = words(text)
    return {" ".join(found[i:i + size]) for i in range(len(found) - size + 1)}


def plain(data):
    """`data` as text when it is UTF-8 with no control, surrogate, private or unassigned character other than tab,
    line feed and carriage return; otherwise None."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    bad = ("Cc", "Cs", "Co", "Cn")
    return None if any(unicodedata.category(c) in bad and c not in "\t\n\r" for c in text) else text


def names(place, name):
    """True when the place holds `name` as words, or as one word squashed together as in `HaikuWriter`, plural
    or not."""
    wanted = words(name)
    phrase, squashed = " ".join(wanted), "".join(wanted)
    return bool(wanted) and (any(f" {phrase}{s} " in f" {place.words} " for s in ("", "s"))
                             or bool({squashed, squashed + "s"} & set(place.words.split())))


def told(place, stem):
    """The words of the place that start with the tell `stem`, such as `evaluator` for `eval`."""
    return set(re.findall(rf"(?:^| )({re.escape(stem)}[^ ]*)", place.words))


def _hash(entry):
    """The sha256 of a regular file's entry, or None for anything else."""
    return entry.split(" ")[1] if manifest.is_file(entry) else None


def copies(case):
    """The world paths that are still byte for byte the copy their case entry records."""
    entries = manifest.manifest(case.world)
    return {c["world"] for c in case.copies if _hash(entries.get(c["world"], "")) == c["source_sha256"]}


def visible(case, arm):
    """Every place the without-skill run of `case` can see, from the built arm `arm`."""
    want, _ = world.expected(case, arm.installs)
    files, _ = arm.read()
    if files != want:
        raise CaseError(f"{case.id}: the built arm is not what the case says")
    targets = [target for install in arm.installs for target in install.targets]
    index = case.index["file"] if case.index else None
    places = [Place(PROMPT_KEY, case.prompt, "case")]
    places += [Place(commit_key(n), c["message"], "case") for n, c in enumerate(case.commits, 1)]
    if case.index:
        places.append(Place(INDEX_ROW, f"{case.index['after']}\n{case.index['row']}", "case"))
    for path, entry in sorted(files.items()):
        installed = any(path == t or path.startswith(t + "/") for t in targets)
        body = ""
        if manifest.kind(entry) == "file":
            data = (case.world if path == index else arm.path).joinpath(path).read_bytes()
            body = data.decode("utf-8", "replace") if installed else plain(data)
        elif manifest.kind(entry) == "link":
            body = entry[len("link "):]
        places.append(Place(path, None if body is None else f"{path}\n{body}", "harness" if installed else "case"))
    rows = [install.row for install in arm.installs if install.row is not None]
    if rows:
        places.append(Place(SIBLING_ROWS, "\n".join(rows), "harness"))
    return places


def texts(folder, keep=lambda path: True):
    """The text of every regular file under `folder` whose relative path `keep` accepts, or none."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return [(folder / p).read_bytes().decode("utf-8", "replace") for p, e in sorted(manifest.manifest(folder).items())
            if manifest.kind(e) == "file" and keep(p)]


def kit_texts(repo=REPO):
    """The measuring kit's text about skills: the files under `evals/skills/`, such as tasks, triggers, checks,
    tests and grading notes, except worlds, cases and upstream sources, which hold project text. The harness's own
    code and notes are general and say nothing about a skill. Checks are standard-library Python, so their import
    lines are left out too."""
    def keep(path):
        return not ({"cases", "files", "upstream", "world"} & set(path.split("/")[1:]))
    folder = Path(repo) / "evals" / "skills"
    return [re.sub(r"(?m)^[ \t]*(?:import|from)[ \t].*$", "", text) for text in texts(folder, keep)]


def shared_runs(places, copied, upstream, size, prompt=True):
    """Runs of project text: verified copies, installed sibling files, the upstream source and, unless `prompt` is
    false, the prompt. A run found there belongs to the project and stays in both arms, so the run rule does not
    count it. Kit text is never the project's, so the prompt is not shared for it. Sibling rows are not project
    text: the case writes their template, and their descriptions are already in the sibling files."""
    project = [p.text for p in places if p.text and (p.key in copied or (p.author == "harness" and p.key !=
                                                     SIBLING_ROWS) or (prompt and p.key == PROMPT_KEY))]
    found = set()
    for text in project + list(upstream):
        found |= {r for n in range(1, size + 1) for r in runs(text, n)} if size < RUN else runs(text, size)
    return found


def lint(case, arm, skill_dir, upstream=(), kit=(), repo=REPO):
    """Every problem with `case`, given its built without-skill arm. An empty list means it passes."""
    places = visible(case, arm)
    copied = copies(case)
    shared = shared_runs(places, copied, upstream, RUN)
    files, _ = skill_files(skill_dir, case.skill)
    skill = set().union(set(), *(runs(data.decode("utf-8", "replace"), RUN) for data in files.values())) - shared
    measuring = set().union(set(), *(runs(t, RUN) for t in kit)) - shared_runs(places, copied, upstream, RUN, False)
    # An expectation shorter than a run is matched whole; one shorter than three words cannot be told apart from
    # ordinary project words, so a judge reads for it instead.
    expected = [words(e if isinstance(e, str) else e["text"]) for e in case.expectations]
    expected = set().union(set(), *(runs(" ".join(e), min(EXPECTATION_RUN, len(e))) for e in expected
                                    if len(e) >= SHORTEST)) - shared_runs(places, copied, upstream, EXPECTATION_RUN)
    sizes = {len(r.split()) for r in expected}
    allowed = {key: [" ".join(words(w)) for w in ws] for key, ws in case.allow_words.items()}
    leaks = [case.skill] + ([case.skill_rel] if case.skill_rel != f"skills/{case.skill}" else [])
    problems = []
    for place in places:
        if place.text is None:
            problems.append(f"{place.key}: not UTF-8 text without control characters; the lint cannot read it as "
                            "the agent would")
            continue
        problems += [f"{place.key}: names the skill ({leak!r})" for leak in leaks if names(place, leak)]
        hits = sorted(skill & runs(place.text, RUN)) if place.key not in copied else []
        if hits:
            problems.append(f"{place.key}: holds {len(hits)} run(s) of the skill's own text, such as {hits[0]!r}")
        if place.author != "case":
            continue
        # A place may hold exactly the words its `allow_words` names, and no other word of the same stem.
        problems += [f"{place.key}: test-tell word {word!r}" for stem in TELLS
                     for word in sorted(told(place, stem) - set(allowed.get(place.key, [])))]
        hits = sorted(measuring & runs(place.text, RUN))
        if hits:
            problems.append(f"{place.key}: holds text of the measuring kit, such as {hits[0]!r}")
        if place.key != PROMPT_KEY and any(expected & runs(place.text, n) for n in sizes):
            problems.append(f"{place.key}: holds expectation text")
    problems += _copies(case, copied, repo)
    return [f"{case.id}: {p}" for p in problems]


def _copies(case, copied, repo):
    problems = []
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
    skills_root = Path(skills_root) if skills_root else Path(repo) / "skills"
    upstream = texts(Path(repo) / "evals" / "skills" / skill / "upstream")
    kit = kit_texts(repo)
    problems = []
    for case in load_cases(skill, cases_root):
        with tempfile.TemporaryDirectory(prefix="hw-lint-") as folder:
            try:
                arm = world.build(case, adapter, Path(folder) / "arm", skills_root)
                problems += lint(case, arm, skills_root / skill, upstream, kit, repo)
            except CaseError as error:
                problems.append(str(error))
    return problems
