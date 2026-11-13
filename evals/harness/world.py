"""Build the two arms of a case from its world, and prove they differ only by the skill (doc 11, Worlds).

Each arm is the world exactly as written, plus its declared git history and the skills it installs. The
without-skill arm installs the siblings. The with-skill arm installs them too, plus the skill: its folder at the
declared path, a copy where the host discovers skills, and one generated index row. A skill brings only the files
git tracks in its folder. When the world has a history, the installs and the index go into one setup commit with
the same message, author and date in both arms, so `git status` is the same in both and the logs have the same shape.

What goes into each arm is worked out once, by `plan`, from the case, the adapter and the skill sources. The
builder carries out the plan. The proof rebuilds what each arm must hold from the case alone: the manifest from the
plan and the written world, and the git history by writing the arm again in a scratch folder. It never reads what
the builder recorded.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

import manifest
from cases import REPO, CaseError, is_path, sha256_bytes
from skills import folders, library, skill_files, structure

# Fixed identity and dates, so the same history gives the same commits in every arm and round.
GIT_ENV = {"GIT_AUTHOR_NAME": "Project Author", "GIT_AUTHOR_EMAIL": "author@example.invalid",
           "GIT_COMMITTER_NAME": "Project Author", "GIT_COMMITTER_EMAIL": "author@example.invalid",
           "GIT_AUTHOR_DATE": "2026-01-05T10:00:00+00:00", "GIT_COMMITTER_DATE": "2026-01-05T10:00:00+00:00",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
# The one commit that holds what the harness adds to a world with a history. It reads as ordinary project work.
SETUP_MESSAGE = "Set up the project"
# Every entry of an arm gets this time, so no file looks newer in one arm than in the other.
ARM_TIME = 1767607200  # 2026-01-05T10:00:00+00:00, as GIT_ENV


class Install:
    """One skill to install: its name, source folder, the arm paths it is copied to, its index row, and its files:
    the manifest of the files git tracks in the source, with their folders."""

    def __init__(self, name, source, targets, row, tracked):
        self.name, self.source, self.targets, self.row = name, Path(source), targets, row
        self.files = {}
        for rel in tracked:
            self.files.update({str(p): "dir" for p in PurePosixPath(rel).parents if str(p) != "."})
            self.files[rel] = manifest.entry(self.source / rel)
        self.files = dict(sorted(self.files.items()))

    def record(self):
        return {"name": self.name, "paths": self.targets, "sha256": manifest.digest(self.files)}


def names(words):
    """A pattern that finds each of `words` (a skill's name and paths) as a whole name: not inside a longer name,
    so a skill named `test` is not found in `pytest` or `test_save`. A name character is an ASCII letter, digit, `_`
    or `-`, the same for text and bytes. The grader view removes each line it finds, and every index row must be
    one (`plan`)."""
    return re.compile("(?<![\\w-])(?:" + "|".join(re.escape(word) for word in words) + ")(?![\\w-])", re.ASCII)


def plan(case, adapter, with_skill, skills_root=None, skill_dir=None):
    """The skills one arm of `case` installs, in order, checked. Raise CaseError when the plan is unsound."""
    known = library(skills_root) if skills_root else folders(REPO)
    if case.kind == "trigger":
        # Trigger worlds install the full skill set, as in real use.
        every = set(known) - {case.skill}
        if set(case.siblings) != every:
            raise CaseError(f"{case.id}: a trigger case installs every other skill as a sibling: missing "
                            f"{sorted(every - set(case.siblings))}, unknown {sorted(set(case.siblings) - every)}")
    missing = [name for name in case.siblings + ([] if skill_dir or not with_skill else [case.skill])
               if name not in known]
    if missing:
        raise CaseError(f"{case.id}: no skill named {missing[0]!r} in the repository")
    wanted = [(name, known[name], f"skills/{name}") for name in case.siblings]
    if with_skill:
        wanted.append((case.skill, Path(skill_dir) if skill_dir else known[case.skill], case.skill_rel))
    world = manifest.manifest(case.world)
    if case.index and world.get(case.index["file"], "").split(" ")[0] != "file":
        raise CaseError(f"{case.id}: the index file {case.index['file']} must be a regular file in the world")
    installs, taken = [], []
    for name, source, rel in wanted:
        files, meta = skill_files(source, name)
        targets = [rel] + [p for p in [_discovery(case, adapter, name)] if p != rel]
        for target in targets:
            clash = [t for t in taken if _overlaps(t, target)] + _blocked(world, target)
            if clash:
                raise CaseError(f"{case.id}: {target} would overlap {clash[0]}")
            taken.append(target)
        row = None
        if case.index:
            row = case.index["row"].format(name=name, path=f"{rel}/SKILL.md", description=meta["description"])
            if not names([name, *targets]).search(row):  # the grader view finds the row only by a whole name
                raise CaseError(f"{case.id}: the index row {row!r} must name {name} or its path as a whole name")
        installs.append(Install(name, source, targets, row, files))
    return installs


def _discovery(case, adapter, name):
    """Where the host discovers the skill, relative to the arm. It must stay inside the arm."""
    root = Path("/arm")
    found = Path(adapter.skill_dir(root, name))
    try:
        relative = found.relative_to(root).as_posix()
    except ValueError:
        relative = None
    if not is_path(relative):
        raise CaseError(f"{case.id}: the host discovers skills at {found}, outside the arm")
    return relative


def _blocked(world, target):
    """World paths in the way of `target`: the path itself, anything under it, or a parent that is not a
    folder (a file, or a link that would send the copy elsewhere)."""
    path = PurePosixPath(target)
    return [p for p, entry in world.items() if p == target or path in PurePosixPath(p).parents
            or (PurePosixPath(p) in path.parents and manifest.kind(entry) != "dir")]


def _overlaps(a, b):
    a, b = PurePosixPath(a), PurePosixPath(b)
    return a == b or a in b.parents or b in a.parents


def with_rows(data, after, rows):
    """`data` (bytes) with `rows` added at the end of the table whose header line is `after`.

    The file is edited as bytes, so its encoding and line endings are kept; each row takes the header's ending. Each
    row is one whole line and the only bytes added, so the grader view, which removes every line naming the skill,
    gives the index back exactly as the without-skill arm has it: a row with a line break, or a table whose last
    line has no ending, is refused.
    """
    lines = data.splitlines(keepends=True)
    header = after.strip().encode()
    at = next((i for i, line in enumerate(lines) if line.strip() == header), None)
    if at is None:
        raise CaseError(f"the index has no line {after!r}")
    ending = lines[at][len(lines[at].rstrip(b"\r\n")):] or b"\n"
    end = at + 1
    while end < len(lines) and lines[end].lstrip().startswith(b"|"):
        end += 1
    if not lines[end - 1].endswith((b"\n", b"\r")):
        raise CaseError(f"the index table under {after!r} must end with a line ending")
    if any(row.splitlines() != [row] for row in rows):
        raise CaseError("an index row must be one line")
    lines[end:end] = [row.encode() + ending for row in rows]
    return b"".join(lines)


def expected(case, installs):
    """The manifest an arm with `installs` must have, without `.git`, and its index text (or None)."""
    entries = manifest.manifest(case.world)
    for install in installs:
        for target in install.targets:
            for parent in PurePosixPath(target).parents:
                if str(parent) != ".":
                    entries.setdefault(str(parent), "dir")
            entries[target] = "dir"
            entries.update({f"{target}/{name}": entry for name, entry in install.files.items()})
    rows = [install.row for install in installs if install.row is not None]
    if not rows:
        return entries, None
    index = case.index["file"]
    text = with_rows((case.world / index).read_bytes(), case.index["after"], rows)
    executable = entries[index].endswith(f" {manifest.EXEC}")
    entries[index] = "file " + sha256_bytes(text) + (f" {manifest.EXEC}" if executable else "")
    return entries, text


class Arm:
    """One built arm: its folder, its manifest without `.git`, the entries of `.git`, and what it installed."""

    def __init__(self, path, arm, installs):
        self.path = Path(path)
        self.arm = arm
        self.installs = installs
        self.files, self.git = self.read()
        self.sha256 = manifest.digest(self.files)

    def read(self):
        """The arm's manifest split in two, as it is on disk now: every entry outside `.git`, and `.git` itself
        with everything under it. A `.git` of any kind, a link or a file included, lands in the second."""
        entries = manifest.manifest(self.path)
        git = {p: e for p, e in entries.items() if p.split("/")[0] == ".git"}
        return {p: e for p, e in entries.items() if p not in git}, git

    def record(self):
        return {"arm": self.arm, "sha256": self.sha256, "skills": [install.record() for install in self.installs]}


def build(case, adapter, out, skills_root=None, with_skill=False, skill_dir=None):
    """Build one arm of `case` for the host of `adapter` in the empty folder `out`: the without-skill arm, or with
    `with_skill` the with-skill arm. `skills_root` is the skills, a folder of them or {name: folder} (`skills.library`),
    by default the repository's (`skills.folders`). `skill_dir` overrides the folder of the skill under test, such as
    a candidate version."""
    out = _empty(out)
    # A written world never holds git metadata, whose hooks would run when the history is built, nor a symlink
    # that leads out of it, which would point the arm back at the source or the machine.
    problems = structure(case.world)
    if problems:
        raise CaseError(f"{case.id}: the world is unsound: {problems}")
    installs = plan(case, adapter, with_skill, skills_root, skill_dir)
    _write(out, case, installs)
    return Arm(out, "with_skill" if with_skill else "without_skill", installs)


def _empty(out):
    out = Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise CaseError(f"{out} is not empty")
    return out


def _write(folder, case, installs):
    """Write an arm in `folder`: the world as written, its declared history, the installs, the index written in
    one step from the written world with every row of the arm, exactly as `expected` does, and the setup commit."""
    shutil.copytree(case.world, folder, symlinks=True, dirs_exist_ok=True)
    _history(folder, case.commits)
    for install in installs:
        for target in install.targets:
            # Only the files the install lists, with their executable bit, so nothing else in the source comes in.
            for rel, entry in install.files.items():
                if manifest.kind(entry) == "dir":
                    (folder / target / rel).mkdir(parents=True, exist_ok=True)
                else:
                    (folder / target / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(install.source / rel, folder / target / rel)
    rows = [install.row for install in installs if install.row is not None]
    if rows:
        text = with_rows((case.world / case.index["file"]).read_bytes(), case.index["after"], rows)
        (folder / case.index["file"]).write_bytes(text)
    if case.commits:
        added = [target for install in installs for target in install.targets]
        added += [case.index["file"]] if case.index else []
        if added:
            _git(folder, "add", "--force", "--", *added)
        _git(folder, "commit", "-q", "--allow-empty", "-m", SETUP_MESSAGE)
        # The index is rebuilt from the head tree with no file times or flags, so it is the same bytes in every
        # copy and is compared like any other file. git refreshes the times on its first status in the arm.
        _git(folder, "read-tree", "HEAD")
    for path in [folder / p for p in manifest.manifest(folder)] + [folder]:
        os.utime(path, (ARM_TIME, ARM_TIME), follow_symlinks=False)


def _git(world, *args):
    """Run git on the repository of `world` only. CaseError when git fails."""
    # Built from an allow list, never inherited: GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE and the like would point
    # git at another repository.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
    env.update(GIT_ENV, HOME=os.devnull)
    try:
        return subprocess.run(["git", f"--git-dir={world / '.git'}", f"--work-tree={world}",
                               "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main",
                               "-c", f"core.hooksPath={os.devnull}", *args],
                              cwd=world, env=env, check=True, capture_output=True, text=True).stdout
    except subprocess.CalledProcessError as error:
        raise CaseError(f"git {args[0]} failed: {error.stderr.strip()}") from None


def _history(world, commits):
    """Build the declared commits in `world`. Without commits, the world gets no `.git` at all."""
    if not commits:
        return
    # No templates: `.git` holds only what the case declares, with no sample hooks or descriptions for a run to read.
    _git(world, "init", "-q", "--template=")
    for commit in commits:
        for path in commit["paths"]:
            if not (world / path).exists():
                raise CaseError(f"commit {commit['message']!r} names {path}, which is not in the world")
        # Forced, so a world .gitignore cannot drop a path the case declares.
        _git(world, "add", "--force", "--", *commit["paths"])
        _git(world, "commit", "-q", "--allow-empty", "-m", commit["message"])


def _replay(case, installs, near):
    """The `.git` entries an arm with `installs` must have, from the arm written again in a scratch folder, and its
    head commit (None without history). The scratch folder sits in `near`, on the arm's own filesystem, so git
    records the same `core.*` settings there as in the arm."""
    if not case.commits:
        return {}, None
    with tempfile.TemporaryDirectory(dir=near) as scratch:
        scratch = Path(scratch)
        _write(scratch, case, installs)
        entries = {p: e for p, e in manifest.manifest(scratch).items() if p.split("/")[0] == ".git"}
        return entries, _git(scratch, "rev-parse", "HEAD").strip()


def prove(case, adapter, base, with_arm, skills_root=None, skill_dir=None):
    """Raise CaseError unless both arms are exactly what the case says. Return the proof record.

    Each arm is read from disk again. Its manifest must equal the one rebuilt from the written world and the plan,
    entry for entry, the index file included. Its `.git` must equal the one written again from the case, entry for
    entry: none of any kind without commits. git never runs on an arm to prove it.
    """
    read, heads = {}, {}
    for arm, with_skill in ((base, False), (with_arm, True)):
        files, git = arm.read()
        installs = plan(case, adapter, with_skill, skills_root, skill_dir)
        want, _ = expected(case, installs)
        missing = sorted(set(want) - set(files))
        extra = sorted(set(files) - set(want))
        differ = sorted(p for p in want if p in files and files[p] != want[p])
        if missing or extra or differ:
            raise CaseError(f"the {arm.arm} arm is not what the case says: missing {missing}, extra {extra}, "
                            f"different {differ}")
        want_git, heads[arm.arm] = _replay(case, installs, arm.path.parent)
        if git != want_git:
            raise CaseError(f"the {arm.arm} arm's git history is not what the case declares")
        read[arm.arm] = want
    return {"without_skill": manifest.digest(read["without_skill"]), "with_skill": manifest.digest(read["with_skill"]),
            "git_heads": heads, "added": sorted(set(read["with_skill"]) - set(read["without_skill"]))}
