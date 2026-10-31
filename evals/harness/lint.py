"""World lint: reject a case whose world or prompt is unsound, before any run (doc 11, World lint).

Run from the repository root:

    python3 evals/harness/lint.py --skill NAME [--host codex]

It builds each case's without-skill arm for the host and prints every problem. Exit code 1 when any case fails.
"""

import argparse
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import REPO, CaseError, load_cases, sha256_file  # noqa: E402

SHINGLE = 8
# Words that tell an agent it is being tested. A file may allow some of them through `allow_words`.
TELLS = ("eval", "evals", "evaluation", "evaluated", "fixture", "fixtures", "grader", "graders", "grading",
         "graded", "benchmark", "benchmarks", "rubric", "golden", "test harness", "harness run")
# File names that belong to the measuring kit and must never be inside a world.
KIT_NAMES = ("case.json", "tasks.json", "triggers.json", "grading.json", "expectations.json", "verdict.json")
KIT_FOLDERS = ("evals", "cases", "goldens", "results")
TEXT_LIMIT = 2_000_000


def words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def shingles(text, size=SHINGLE):
    found = words(text)
    return {" ".join(found[i:i + size]) for i in range(len(found) - size + 1)}


def text_files(folder, skip=(".git",)):
    """{relative path: text} for every readable text file under `folder`."""
    found = {}
    for path in sorted(Path(folder).rglob("*")):
        relative = path.relative_to(folder)
        if relative.parts[0] in skip or path.is_symlink() or not path.is_file():
            continue
        if path.stat().st_size > TEXT_LIMIT:
            continue
        try:
            found[relative.as_posix()] = path.read_text()
        except UnicodeDecodeError:
            continue
    return found


def fingerprint(skill_dir, documents, upstream_dir, prompt):
    """Every 8-word run of the skill's text that is the skill's own.

    Runs that also appear in the world's copied project documents, in the skill's recorded upstream source or in
    the prompt are left out: that text belongs to the project, the source or the task, and stays in both arms.
    """
    own = set()
    for text in text_files(skill_dir).values():
        own |= shingles(text)
    shared = shingles(prompt)
    for text in documents:
        shared |= shingles(text)
    if upstream_dir and Path(upstream_dir).is_dir():
        for text in text_files(upstream_dir).values():
            shared |= shingles(text)
    return own - shared


def lint(case, base_world, skill_dir, upstream_dir=None, repo=REPO):
    """Every problem with `case`, given its built without-skill arm. An empty list means it passes."""
    problems = []
    files = text_files(base_world)
    prompt = case.prompt
    copied = {copy["world"] for copy in case.copies}
    allow = {path: {w.lower() for w in allowed} for path, allowed in case.allow_words.items()}

    authored = text_files(case.world)
    leaks = [case.skill.lower(), case.skill_rel.lower()]
    for path, text in list(files.items()) + [("<prompt>", prompt)]:
        for leak in leaks:
            if leak in text.lower():
                problems.append(f"{path}: names the skill ({leak!r})")
    # Test tells and eval files are looked for in what the case author wrote. Installed sibling skills are
    # real project content and may talk about evals; they are checked for the skill's name and text above.
    for path, text in list(authored.items()) + [("<prompt>", prompt)]:
        lowered = text.lower()
        for tell in TELLS:
            if tell not in allow.get(path, set()) and re.search(rf"\b{re.escape(tell)}\b", lowered):
                problems.append(f"{path}: test-tell word {tell!r}")

    marks = fingerprint(skill_dir, [files[p] for p in copied if p in files], upstream_dir, prompt)
    for path, text in files.items():
        if path in copied:
            continue
        hits = marks & shingles(text)
        if hits:
            problems.append(f"{path}: holds {len(hits)} run(s) of the skill's own text, such as {sorted(hits)[0]!r}")

    expectation_runs = set()
    for expectation in case.expectations:
        text = expectation if isinstance(expectation, str) else str(expectation.get("text", ""))
        expectation_runs |= shingles(text, 6)
    for path, text in authored.items():
        parts = Path(path).parts
        if Path(path).name in KIT_NAMES or any(part in KIT_FOLDERS for part in parts[:-1]):
            problems.append(f"{path}: an eval file inside the world")
        if expectation_runs & shingles(text, 6):
            problems.append(f"{path}: holds expectation text")

    problems += _structure(case.world)
    for copy in case.copies:
        source = Path(repo) / copy["source"]
        if not (case.world / copy["world"]).is_file():
            problems.append(f"copy {copy['world']}: not in the world")
        elif not source.is_file():
            problems.append(f"copy {copy['world']}: source {copy['source']} no longer exists")
        elif sha256_file(source) != copy["source_sha256"]:
            problems.append(f"copy {copy['world']}: {copy['source']} changed since it was copied; review the copy "
                            "and record the new source_sha256")
    return [f"{case.id}: {p}" for p in problems]


def _structure(world):
    """A `.git` folder, or a symlink that points outside the world, in the written world."""
    problems = []
    root = Path(world).resolve()
    for path in sorted(Path(world).rglob("*")):
        relative = path.relative_to(world).as_posix()
        if path.name == ".git":
            problems.append(f"{relative}: a .git folder; declare history as commits in case.json")
        if path.is_symlink():
            target = (path.parent / path.readlink()).resolve()
            if not target.is_relative_to(root):
                problems.append(f"{relative}: a symlink that points outside the world")
    return problems


def lint_skill(skill, adapter, cases_root=None, skills_root=None):
    """Lint every case of a skill for one host. Returns the problems."""
    import world as world_builder
    skills_root = Path(skills_root) if skills_root else REPO / "skills"
    upstream = REPO / "evals" / "skills" / skill / "upstream"
    problems = []
    for case in load_cases(skill, cases_root):
        with tempfile.TemporaryDirectory(prefix="hw-lint-") as folder:
            try:
                arm = world_builder.build(case, adapter, Path(folder) / "w", False, skills_root)
            except CaseError as error:
                problems.append(str(error))
                continue
            problems += lint(case, arm.path, skills_root / skill, upstream)
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skill", required=True)
    parser.add_argument("--host", default="claude-code")
    args = parser.parse_args(argv)
    import hosts
    try:
        problems = lint_skill(args.skill, hosts.load(args.host))
    except CaseError as error:
        problems = [str(error)]
    for problem in problems:
        print(problem)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
