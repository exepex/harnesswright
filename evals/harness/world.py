"""Build the two arms of a case from its world, and prove they differ only by the skill (doc 11, Worlds).

The without-skill arm (the base) is the world exactly as written, plus its declared git history and sibling
skills. The with-skill arm is a copy of the built base, plus the skill: its folder at the declared path, a copy
where the host discovers skills, and one generated index row. Nothing is ever removed.

What goes into each arm is worked out once, by `plan`, from the case, the adapter and the skill sources. The
builder carries out the plan. The proof rebuilds what each arm must hold from the case alone: the manifest from the
plan and the written world, and the git history by replaying the declared commits in a scratch copy. It never reads
what the builder recorded.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

import manifest
from cases import REPO, CaseError, is_path, sha256_bytes
from skills import skill_files, structure

# Fixed identity and dates, so the same history gives the same commits in every arm and round.
GIT_ENV = {"GIT_AUTHOR_NAME": "Project Author", "GIT_AUTHOR_EMAIL": "author@example.invalid",
           "GIT_COMMITTER_NAME": "Project Author", "GIT_COMMITTER_EMAIL": "author@example.invalid",
           "GIT_AUTHOR_DATE": "2026-01-05T10:00:00+00:00", "GIT_COMMITTER_DATE": "2026-01-05T10:00:00+00:00",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}


class Install:
    """One skill to install: its name, source folder, the arm paths it is copied to, and its index row."""

    def __init__(self, name, source, targets, row):
        self.name, self.source, self.targets, self.row = name, Path(source), targets, row
        self.files = manifest.manifest(self.source)

    def record(self):
        return {"name": self.name, "paths": self.targets, "sha256": manifest.digest(self.files)}


def plan(case, adapter, with_skill, skills_root=None, skill_dir=None):
    """The skills one arm of `case` installs, in order, checked. Raise CaseError when the plan is unsound."""
    skills_root = Path(skills_root) if skills_root else REPO / "skills"
    if case.kind == "trigger":
        # Trigger worlds install the full skill set, as in real use.
        every = {p.name for p in skills_root.iterdir() if (p / "SKILL.md").is_file()} - {case.skill}
        if set(case.siblings) != every:
            raise CaseError(f"{case.id}: a trigger case installs every other skill as a sibling: missing "
                            f"{sorted(every - set(case.siblings))}, unknown {sorted(set(case.siblings) - every)}")
    wanted = [(name, skills_root / name, f"skills/{name}") for name in case.siblings]
    if with_skill:
        wanted.append((case.skill, Path(skill_dir) if skill_dir else skills_root / case.skill, case.skill_rel))
    world = manifest.manifest(case.world)
    if case.index and world.get(case.index["file"], "").split(" ")[0] != "file":
        raise CaseError(f"{case.id}: the index file {case.index['file']} must be a regular file in the world")
    installs, taken = [], []
    for name, source, rel in wanted:
        _, meta = skill_files(source, name)
        targets = [rel] + [p for p in [_discovery(case, adapter, name)] if p != rel]
        for target in targets:
            clash = [t for t in taken if _overlaps(t, target)] + _blocked(world, target)
            if clash:
                raise CaseError(f"{case.id}: {target} would overlap {clash[0]}")
            taken.append(target)
        row = None
        if case.index:
            row = case.index["row"].format(name=name, path=f"{rel}/SKILL.md", description=meta["description"])
        installs.append(Install(name, source, targets, row))
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

    The file is edited as bytes, so its encoding and line endings are kept; each row takes the header's ending.
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
        lines[end - 1] += ending
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


def build(case, adapter, out, skills_root=None):
    """Build the without-skill arm of `case` for the host of `adapter` in the empty folder `out`."""
    out = _empty(out)
    # A written world never holds git metadata, whose hooks would run when the history is built, nor a symlink
    # that leads out of it, which would point the arm back at the source or the machine.
    problems = structure(case.world)
    if problems:
        raise CaseError(f"{case.id}: the world is unsound: {problems}")
    installs = plan(case, adapter, False, skills_root)
    shutil.copytree(case.world, out, symlinks=True, dirs_exist_ok=True)
    _history(out, case.commits)
    _install(out, case, installs, installs)
    return Arm(out, "without_skill", installs)


def add_skill(base, case, adapter, out, skills_root=None, skill_dir=None):
    """Build the with-skill arm in the empty folder `out`: a copy of the built `base`, plus the skill.

    `skill_dir` overrides the folder of the skill under test, such as a candidate version.
    """
    out = _empty(out)
    installs = plan(case, adapter, True, skills_root, skill_dir)
    shutil.copytree(base.path, out, symlinks=True, dirs_exist_ok=True)
    _install(out, case, installs[len(base.installs):], installs)
    return Arm(out, "with_skill", installs)


def _empty(out):
    out = Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise CaseError(f"{out} is not empty")
    return out


def _install(arm, case, new, every):
    """Copy the `new` installs into the arm, and write the index from the written world with the rows of `every`
    install of the arm, in one step, exactly as `expected` does."""
    for install in new:
        for target in install.targets:
            # Copied as it is: modes kept, so a script stays executable, and links kept as links.
            shutil.copytree(install.source, arm / target, symlinks=True)
    rows = [install.row for install in every if install.row is not None]
    if rows:
        text = with_rows((case.world / case.index["file"]).read_bytes(), case.index["after"], rows)
        (arm / case.index["file"]).write_bytes(text)


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
    # The index is rebuilt from the head tree with no file times or flags, so it is the same bytes in every copy and
    # is compared like any other file. git refreshes the times on its first status in the arm.
    _git(world, "read-tree", "HEAD")


def _replay(case, near):
    """The `.git` entries every arm of `case` must have, from the declared commits replayed in a scratch copy of the
    world, and the head commit (None without history). The copy sits in the folder `near`, on the arm's own
    filesystem, so git records the same `core.*` settings there as in the arm."""
    if not case.commits:
        return {}, None
    with tempfile.TemporaryDirectory(dir=near) as scratch:
        scratch = Path(scratch)
        shutil.copytree(case.world, scratch, symlinks=True, dirs_exist_ok=True)
        _history(scratch, case.commits)
        entries = {p: e for p, e in manifest.manifest(scratch).items() if p.split("/")[0] == ".git"}
        return entries, _git(scratch, "rev-parse", "HEAD").strip()


def prove(case, adapter, base, with_arm, skills_root=None, skill_dir=None):
    """Raise CaseError unless both arms are exactly what the case says. Return the proof record.

    Each arm is read from disk again. Its manifest must equal the one rebuilt from the written world and the plan,
    entry for entry, the index file included. Its `.git` must equal the one replayed from the declared commits,
    entry for entry: none of any kind without commits. git never runs on an arm to prove it.
    """
    want_git, head = _replay(case, base.path.parent)
    read = {}
    for arm, with_skill in ((base, False), (with_arm, True)):
        files, git = arm.read()
        want, _ = expected(case, plan(case, adapter, with_skill, skills_root, skill_dir))
        missing = sorted(set(want) - set(files))
        extra = sorted(set(files) - set(want))
        differ = sorted(p for p in want if p in files and files[p] != want[p])
        if missing or extra or differ:
            raise CaseError(f"the {arm.arm} arm is not what the case says: missing {missing}, extra {extra}, "
                            f"different {differ}")
        if git != want_git:
            raise CaseError(f"the {arm.arm} arm's git history is not what the case declares")
        read[arm.arm] = want
    return {"without_skill": manifest.digest(read["without_skill"]), "with_skill": manifest.digest(read["with_skill"]),
            "git_head": head, "added": sorted(set(read["with_skill"]) - set(read["without_skill"]))}
