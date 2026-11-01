"""World lint: reject a case whose world or prompt is unsound, before any run (doc 11, World lint).

`lint_case` lints a case as it will run: it builds both arms with the skill folder the run uses, proves each is
exactly what the case says, and only then reads the without-skill arm. Every rule reads one list, `visible`: each
place that run can see. A place has a kind:

- `world`: a world entry, its path and its text or link target, copies included;
- `declared`: the prompt, a commit message, or the index row template the case writes;
- `installed`: a file of an installed sibling skill;
- `rows`: the index rows of the installed siblings, as the run reads them: the case's row template filled with
  each sibling's name, path and description.

`RULES` says which rules read which kind. `world` and `declared` places are what the case author wrote, so every
rule reads them. `installed` places are real project content, checked for the skill only. `rows` mix the two, so
every rule but the tells reads them: a tell inside a sibling's description is the project's own word.

Every text rule is one rule: protected text, minus project text, found in a place. Project text is computed once:
verified copies, installed sibling files, the recorded upstream source and the standard licence texts in
`evals/fixtures/licences/`. It stays in both arms, so it never counts. The prompt is never project text: the case
author writes it for this case.

What the lint reads is what an agent reads: every world file must be UTF-8 text with no control character other
than tab, line feed and carriage return. A file in any other form, such as UTF-16, an archive or a binary, is
refused rather than guessed at. Text is matched after Unicode compatibility folding, with format characters such
as soft hyphens removed, so look-alike spellings match too.
"""

import io
import json
import re
import tempfile
import tokenize
import unicodedata
from pathlib import Path

import checks
import manifest
import world
from cases import PROMPT_KEY, REPO, Case, CaseError, commit_key, is_plain, sha256_bytes
from skills import skill_files, skill_names, tracked, tracked_file

RUN = 8
EXPECTATION_RUN = 6
SHORTEST = 3
# Tell stems (doc 11): a word that starts with one tells an agent it is being tested. `allow_words` lets a place
# hold the words it names. `.harness/runs/` is the project's own run folder (doc 06), so no stem matches it.
TELLS = ("eval", "fixture", "grader", "grading", "graded", "benchmark", "rubric", "golden", "test harness",
         "ground truth", "expected output")
# Eval text (doc 11) is text about skills and their cases, which tells an agent what is measured: every file under
# `evals/` but the folders of `MACHINERY`, the harness and runner, which are general and say nothing about a skill.
# A new kit part, such as goldens or the grader prompt, counts without being listed. `PROJECT_TEXT` folders, paths
# under `evals/` where None is any name, hold text written for worlds. Case data is the files that hold cases, new
# and old; each holds prompts and histories, which a ported or sibling case may repeat.
MACHINERY = ("harness", "runner")
PROJECT_TEXT = (("fixtures",), ("skills", None, "files"), ("skills", None, "upstream"),
                ("skills", None, "cases", None, "world"))
CASE_DATA = ("case.json", "tasks.json", "triggers.json")
# The rules each kind of place is read by.
EVERY = ("names", "skill", "tells", "eval", "expectations")
RULES = {"world": EVERY, "declared": EVERY, "installed": ("names", "skill"),
         "rows": ("names", "skill", "eval", "expectations")}
# Standard licence texts, recorded once. Their terms are project text: a skill and a world may both carry the same
# licence. Only text found in them is excused, never a file by its name.
LICENCES = ("evals", "fixtures", "licences")
INDEX_ROW = "<index row>"
SIBLING_ROWS = "<sibling rows>"


class Place:
    """One thing the run can see: where it is, its text (None when the file is not plain text), and its kind."""

    def __init__(self, key, text, kind):
        self.key, self.text, self.kind = key, text, kind
        self.link = False
        self.words = " ".join(words(text or ""))


def words(text):
    """The words of `text` after compatibility folding, with format characters removed: lower-case runs of
    letters and digits in any script. `haiku-writer`, `Haiku_Writer` and `haiku writer` are the same words."""
    folded = "".join(c for c in unicodedata.normalize("NFKC", text) if unicodedata.category(c) != "Cf")
    # ASCII letters and digits form words of their own, so a name written flush against text in another script,
    # as in Chinese or Japanese prose, is still a word.
    return re.findall(r"[a-z0-9]+|[^\W_a-z0-9]+", folded.casefold())


def runs(text, sizes):
    """Every run of consecutive words of `text` whose length is one of `sizes`."""
    found = words(text)
    return {" ".join(found[i:i + n]) for n in sizes for i in range(len(found) - n + 1)}


def all_runs(texts, sizes):
    return set().union(set(), *(runs(t, sizes) for t in texts))


def plain(data):
    """`data` as text when it is UTF-8 and plain (`cases.is_plain`); otherwise None."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text if is_plain(text) else None


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


def visible(case, arm):
    """Every place the without-skill run of `case` can see, from its built and proved arm `arm`."""
    files, _ = arm.read()
    targets = [target for install in arm.installs for target in install.targets]
    index = case.index["file"] if case.index else None
    places = [Place(PROMPT_KEY, case.prompt, "declared")]
    places += [Place(commit_key(n), c["message"], "declared") for n, c in enumerate(case.commits, 1)]
    if case.index:
        places.append(Place(INDEX_ROW, f"{case.index['after']}\n{case.index['row']}", "declared"))
    for path, entry in sorted(files.items()):
        installed = any(path == t or path.startswith(t + "/") for t in targets)
        body = ""
        if manifest.kind(entry) == "file":
            data = (case.world if path == index else arm.path).joinpath(path).read_bytes()
            body = data.decode("utf-8", "replace") if installed else plain(data)
        elif manifest.kind(entry) == "link":
            body = entry[len("link "):]
        places.append(Place(path, None if body is None else f"{path}\n{body}", "installed" if installed else "world"))
        places[-1].link = manifest.kind(entry) == "link"
    rows = [install.row for install in arm.installs if install.row is not None]
    if rows:
        places.append(Place(SIBLING_ROWS, "\n".join(rows), "rows"))
    return places


def texts(folder):
    """The text of every regular file under `folder`, or none."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return [(folder / p).read_bytes().decode("utf-8", "replace") for p, e in sorted(manifest.manifest(folder).items())
            if manifest.kind(e) == "file"]


def _project_text(parts):
    """True when `parts`, a file's path under `evals/`, is inside a folder of `PROJECT_TEXT`."""
    return any(len(parts) > len(t) and all(w in (None, part) for w, part in zip(t, parts)) for t in PROJECT_TEXT)


# Python tokens that hold text: strings, comments and, from Python 3.12, the text parts of f-strings.
TEXT_TOKENS = {tokenize.STRING, tokenize.COMMENT, getattr(tokenize, "FSTRING_MIDDLE", tokenize.STRING)}


def said(path, text):
    """What a file says: for Python, its strings and comments, since its code is the same in any Python program;
    for anything else, or Python that does not parse, all of it."""
    if path.suffix != ".py":
        return text
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError):
        return text
    return "\n".join(t.string for t in tokens if t.type in TEXT_TOKENS)


def eval_texts(repo=REPO):
    """The eval text under `repo`: (measuring, cases). `measuring` is what every file under `evals/` but machinery,
    case data and project text says. `cases` is each case data file as (path, text)."""
    measuring, cases = [], []
    for path in sorted((Path(repo) / "evals").glob("**/*")):
        parts = path.relative_to(Path(repo) / "evals").parts
        if not path.is_file() or path.is_symlink() or parts[0] in MACHINERY or _project_text(parts):
            continue
        text = path.read_bytes().decode("utf-8", "replace")
        if parts[0] == "skills" and path.name in CASE_DATA:
            cases.append((path, text))
        else:
            measuring.append(said(path, text))
    return measuring, sorted(cases)


def verified_copies(case, repo=REPO):
    """(verified, problems): the world paths that are their recorded source as git tracks it, and a problem for
    every other copy.

    The source is read only as a file git tracks in `repo`, through real folders, so a link, an untracked file or a
    path spelled in another case cannot bring skill or eval text in as a copy. Its hash must still be the recorded
    `source_sha256`. The world file must be the source with its skill rows removed: each table row that names a
    skill of the repository, which the index rows of the arm replace."""
    verified, problems = set(), []
    if not case.copies:
        return verified, problems
    known = set(tracked(repo))
    skills = skill_names(Path(repo) / "skills") if (Path(repo) / "skills").is_dir() else []
    for copy in case.copies:
        try:
            source = tracked_file(repo, copy["source"]) if copy["source"] in known else None
        except CaseError:
            source = None
        try:
            entry = manifest.entry(case.world / copy["world"])
        except manifest.Unreadable:
            entry = ""
        written = (case.world / copy["world"]).read_bytes() if manifest.is_file(entry) else None
        if source is None:
            problems.append(f"copy {copy['world']}: source {copy['source']} is not a regular file git tracks")
        elif sha256_bytes(source) != copy["source_sha256"]:
            problems.append(f"copy {copy['world']}: {copy['source']} changed since it was copied; review the copy "
                            "and record the new source_sha256")
        elif written != without_skill_rows(source, skills):
            problems.append(f"copy {copy['world']}: not its source with the skill rows removed")
        else:
            verified.add(copy["world"])
    return verified, problems


def without_skill_rows(data, skills):
    """`data` (bytes) without each table row, a line starting with `|`, that names one of `skills`."""
    lines = data.splitlines(keepends=True)
    return b"".join(line for line in lines if not (line.lstrip().startswith(b"|") and any(
        names(Place("", line.decode("utf-8", "replace"), "rows"), skill) for skill in skills)))


def citations(case, places):
    """(quotes, problems): for each expectation, the quote of its contract when a world text file holds it where it
    is cited, else None; and a problem for each quote not held there, and for each check whose name or arguments
    are not in the check library. A quote starts on its line, in the words the lint reads, and may run on over the
    lines after it."""
    found, problems, library = [], [], None
    documents = {p.key: p.text.split("\n", 1)[1] for p in places
                 if p.kind == "world" and p.text is not None and not p.link}
    for number, expectation in enumerate(case.expectations, 1):
        if "check" in expectation:
            try:
                library = checks.library() if library is None else library
                checks.validate(expectation["check"]["name"], expectation["check"]["args"], library)
            except checks.CheckError as error:
                problems.append(f"expectation {number}: {error}")
        source = expectation["source"]
        found.append(None)
        if source == "format":
            continue
        path, line, quote = source["contract"]["path"], source["contract"]["line"], source["contract"]["quote"]
        rows = documents[path].splitlines() if path in documents else []
        here = " ".join(words(rows[line - 1])) if line <= len(rows) else ""
        rest, said = " ".join(words("\n".join(rows[line - 1:]))), " ".join(words(quote))
        at = f" {rest} ".find(f" {said} ")  # where the quote's first word starts in `rest`, or -1
        if len(said.split()) < SHORTEST or not here or not 0 <= at < len(here):
            problems.append(f"expectation {number}: {path}:{line} does not start the quote {quote[:80]!r}, of at "
                            f"least {SHORTEST} words" + ("" if path in documents else f"; no world text file {path}"))
            continue
        found[-1] = quote
    return found, problems


def expectation_texts(expectation):
    """Every text an expectation holds: what it says, and its judged question, rules and examples."""
    judged = expectation.get("judged") or {}
    examples = judged.get("examples", {})
    return [expectation["text"]] + [judged[k] for k in ("question", "pass", "fail") if k in judged] \
        + examples.get("pass", []) + examples.get("fail", [])


def stated_quotes(text):
    """The contract quotes a case data file states, or none when it is not a case.json of that shape."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    found = data.get("expectations") if isinstance(data, dict) else None
    if not isinstance(found, list):
        return []
    return [e["source"]["contract"]["quote"] for e in found if isinstance(e, dict) and isinstance(e.get("source"), dict)
            and isinstance(e["source"].get("contract"), dict) and isinstance(e["source"]["contract"].get("quote"), str)]


def lint(case, arm, skill_dir, upstream=(), kit=(), repo=REPO, cases=()):
    """Every problem with `case`, given its built and proved without-skill arm and the eval text: `kit`, the
    measuring texts, and `cases`, the case data as (path, text). An empty list means it passes."""
    places = visible(case, arm)
    copied, problems = verified_copies(case, repo)
    # An expectation shorter than a run is matched whole; one shorter than three words cannot be told apart from
    # ordinary project words, so a judge reads for it instead.
    quotes, cited = citations(case, places)
    problems += cited
    # Every text of an expectation is expectation text: what it says, and its question, rules and examples.
    expectations = [[" ".join(words(t)) for t in expectation_texts(e) if len(words(t)) >= SHORTEST]
                    for e in case.expectations]
    expected_sizes = {min(EXPECTATION_RUN, len(t.split())) for texts_ in expectations for t in texts_}
    project = all_runs([p.text for p in places if p.text and (p.key in copied or p.kind == "installed")]
                       + list(upstream) + texts(Path(repo).joinpath(*LICENCES)), {RUN} | expected_sizes)
    files, _ = skill_files(skill_dir, case.skill)
    skill = all_runs((data.decode("utf-8", "replace") for data in files.values()), {RUN}) - project
    # Case data may repeat what the run sees of this case outside its world (its prompt, commits and index row)
    # and every path, which old task lists name. The rest of the eval text may not. The case's own file is case
    # data like any other, wherever it lives.
    # A quote excuses only itself: the runs of its words, in the case data file that cites it and in the
    # expectation that cites it. Nothing else is excused. This case's quotes count only where the world holds them;
    # another case's are checked when that case is linted.
    cited_quotes = [q for q in quotes if q]
    declared = all_runs([p.key for p in places] + [p.text for p in places if p.kind == "declared"], {RUN})
    mine = (case.folder / "case.json").resolve()
    own = all_runs([mine.read_bytes().decode("utf-8", "replace")], {RUN}) - all_runs(cited_quotes, {RUN})
    data = own.union(*(all_runs([t], {RUN}) - all_runs(stated_quotes(t), {RUN})
                       for path, t in cases if Path(path).resolve() != mine))
    measuring = (all_runs(kit, {RUN}) | (data - declared)) - project
    # An expectation may restate the rule it cites: the world already says it there.
    expected = set().union(set(), *(runs(t, {min(EXPECTATION_RUN, len(t.split()))}) - all_runs([q or ""],
                                                                                              expected_sizes)
                                    for texts_, q in zip(expectations, quotes) for t in texts_)) - project
    allowed = {key: [" ".join(words(w)) for w in ws] for key, ws in case.allow_words.items()}
    # The index row is written into the index file, so it has that file's allowances.
    if case.index:
        allowed[INDEX_ROW] = allowed.get(case.index["file"], [])
    leaks = [case.skill] + ([case.skill_rel] if case.skill_rel != f"skills/{case.skill}" else [])
    for place in places:
        if place.text is None:
            problems.append(f"{place.key}: not UTF-8 text without control characters; the lint cannot read it as "
                            "the agent would")
            continue
        rules = RULES[place.kind]
        # A sibling's own file naming the skill is the sibling's fault; any other place is the case's to fix.
        named = ("a sibling skill names {!r}; skills must never name each other" if place.kind == "installed"
                 else "names the skill ({!r})")
        if "names" in rules:
            problems += [f"{place.key}: {named.format(leak)}" for leak in leaks if names(place, leak)]
        hits = sorted(skill & runs(place.text, {RUN}))
        if hits and "skill" in rules:
            problems.append(f"{place.key}: holds {len(hits)} run(s) of the skill's own text, such as {hits[0]!r}")
        if "tells" in rules:
            # A place may hold exactly the words its `allow_words` names, and no other word of the same stem.
            problems += [f"{place.key}: test-tell word {word!r}" for stem in TELLS
                         for word in sorted(told(place, stem) - set(allowed.get(place.key, [])))]
        hits = sorted(measuring & runs(place.text, {RUN}))
        if hits and "eval" in rules:
            problems.append(f"{place.key}: holds eval text, such as {hits[0]!r}")
        if "expectations" in rules and place.key != PROMPT_KEY and expected & runs(place.text, expected_sizes):
            problems.append(f"{place.key}: holds expectation text")
    return [f"{case.id}: {p}" for p in problems]


def lint_case(case, adapter, out, skills_root, skill_dir=None, upstream=(), kit=(), repo=REPO, cases=()):
    """Lint `case` as it will run: build both arms in the empty folder `out` with `skill_dir`, the skill folder the
    run uses, prove them, and lint the without-skill arm. Raise CaseError when the case cannot run."""
    skill_dir = Path(skill_dir) if skill_dir else Path(skills_root) / case.skill
    base = world.build(case, adapter, Path(out) / "without", skills_root)
    with_arm = world.build(case, adapter, Path(out) / "with", skills_root, True, skill_dir)
    world.prove(case, adapter, base, with_arm, skills_root, skill_dir)
    return lint(case, base, skill_dir, upstream, kit, repo, cases)


def lint_skill(skill, adapter, cases_root=None, skills_root=None, repo=REPO, skill_dir=None):
    """Lint every case of a skill for the host of `adapter`, as `lint_case` does. `skill_dir` is the skill folder
    the run will use, such as a candidate version. Each case is read and built on its own, so a case that cannot be
    is listed and the others are still linted. Returns the problems; none means every case may run."""
    skills_root = Path(skills_root) if skills_root else Path(repo) / "skills"
    cases_root = Path(cases_root) if cases_root else Path(repo) / "evals" / "skills" / skill / "cases"
    if not cases_root.is_dir():
        return [f"{skill}: no cases folder at {cases_root}"]
    upstream = texts(Path(repo) / "evals" / "skills" / skill / "upstream")
    kit, data = eval_texts(repo)
    problems = []
    for folder in sorted(f for f in cases_root.iterdir() if f.is_dir()):
        with tempfile.TemporaryDirectory(prefix="hw-lint-") as out:
            try:
                problems += lint_case(Case(folder, skill), adapter, out, skills_root, skill_dir, upstream, kit, repo,
                                      data)
            except CaseError as error:
                reason = str(error)
                problems.append(reason if reason.startswith(f"{folder.name}: ") else f"{folder.name}: {reason}")
    return problems
