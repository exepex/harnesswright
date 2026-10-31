"""Build the two arms of a case from its world, and prove they differ only by the skill.

The without-skill arm is the world exactly as written, plus its declared git history and sibling skills. The
with-skill arm is the same, plus the skill: its folder at the declared path, a copy where the host discovers
skills, and one generated index row. Nothing is ever removed, so there is no list of lines to get wrong
(doc 11, Worlds).
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path, PurePosixPath

import manifest
from cases import REPO, CaseError, sha256_bytes, skill_files, structure

# Fixed identity and dates, so the same history gives the same commits in every arm and round.
GIT_ENV = {"GIT_AUTHOR_NAME": "Project Author", "GIT_AUTHOR_EMAIL": "author@example.invalid",
           "GIT_COMMITTER_NAME": "Project Author", "GIT_COMMITTER_EMAIL": "author@example.invalid",
           "GIT_AUTHOR_DATE": "2026-01-05T10:00:00+00:00", "GIT_COMMITTER_DATE": "2026-01-05T10:00:00+00:00",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}


class Arm:
    """One built arm: its folder, its file hashes and what was added on top of the written world."""

    def __init__(self, path, arm, overlay, head):
        self.path = Path(path)
        self.arm = arm
        self.overlay = overlay
        self.head = head
        self.files = manifest.manifest(self.path, skip=(".git",))
        self.sha256 = manifest.digest(self.files)

    def record(self):
        return {"arm": self.arm, "sha256": self.sha256, "git_head": self.head, "overlay": self.overlay}


def build(case, adapter, out, with_skill, skills_root=None, skill_dir=None):
    """Build one arm of `case` for the host of `adapter` in the empty folder `out`.

    `skills_root` holds the skills by name (default this repository's `skills/`); `skill_dir` overrides the
    folder of the skill under test, such as a candidate version.
    """
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise CaseError(f"{out} is not empty")
    # A written world never holds git metadata, whose hooks would run when the history is built, nor a symlink
    # that leads out of it, which would point the arm back at the source or the machine.
    problems = structure(case.world)
    if problems:
        raise CaseError(f"{case.id}: the world is unsound: {problems}")
    shutil.copytree(case.world, out, symlinks=True, dirs_exist_ok=True)
    head = _history(out, case.commits)
    skills_root = Path(skills_root) if skills_root else REPO / "skills"
    overlay = {"skills": [], "rows": []}
    for name in case.siblings:
        _install(out, case, adapter, skills_root / name, f"skills/{name}", overlay)
    if with_skill:
        _install(out, case, adapter, Path(skill_dir) if skill_dir else skills_root / case.skill,
                 case.skill_rel, overlay)
    return Arm(out, "with_skill" if with_skill else "without_skill", overlay, head)


def _install(world, case, adapter, source, rel, overlay):
    files, meta = skill_files(source)
    targets = [rel]
    discovery = Path(adapter.skill_dir(world, meta["name"])).relative_to(world).as_posix()
    if discovery != rel:
        targets.append(discovery)
    for target in targets:
        if (world / target).exists():
            raise CaseError(f"{case.id}: {target} already exists in the world")
        for name, data in files.items():
            path = world / target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            # Keep the source's permission bits, so a skill's executable script stays executable.
            path.chmod(stat.S_IMODE((Path(source) / name).stat().st_mode))
    row = None
    if case.index:
        row = case.index["row"].format(name=meta["name"], path=f"{rel}/SKILL.md", description=meta["description"])
        add_row(world / case.index["file"], case.index["after"], row)
    overlay["skills"].append({"name": meta["name"], "paths": targets,
                              "sha256": manifest.digest({k: "file " + sha256_bytes(v) for k, v in files.items()})})
    overlay["rows"].append(row)


def add_row(index_file, after, row):
    """Insert `row` at the end of the table whose header line is `after`."""
    if not index_file.is_file():
        raise CaseError(f"index file {index_file.name} is not in the world")
    lines = index_file.read_text().split("\n")
    try:
        at = next(i for i, line in enumerate(lines) if line.strip() == after.strip())
    except StopIteration:
        raise CaseError(f"{index_file.name} has no line {after!r}") from None
    end = at + 1
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    lines.insert(end, row)
    index_file.write_text("\n".join(lines))


def _history(world, commits):
    """Build the declared commits in `world`; return the head commit, or None without history."""
    if not commits:
        return None
    # Built from an allow list, never inherited: GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE and the like would point
    # git at another repository.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
    env.update(GIT_ENV, HOME=os.devnull)

    def git(*args):
        return subprocess.run(["git", f"--git-dir={world / '.git'}", f"--work-tree={world}",
                               "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main",
                               "-c", f"core.hooksPath={os.devnull}", *args],
                              cwd=world, env=env, check=True, capture_output=True, text=True).stdout.strip()

    git("init", "-q")
    for commit in commits:
        for path in commit["paths"]:
            if not (world / path).exists():
                raise CaseError(f"commit {commit['message']!r} names {path}, which is not in the world")
        git("add", "--", *commit["paths"])
        git("commit", "-q", "--allow-empty", "-m", commit["message"])
    return git("rev-parse", "HEAD")


def prove(base, with_arm):
    """Raise CaseError unless `with_arm` is `base` plus exactly its overlay. Return the proof record.

    Checked from the two manifests, not from what the builder says it did. Nothing of the base is removed. At most
    one entry changes: a file, the index file, whose executable bit is the same and whose text gains exactly the
    overlay's rows. Every added entry is an overlay path, lies under one, or is a folder on the way to one. Both
    arms have the same git head.
    """
    if base.head != with_arm.head:
        raise CaseError("the arms have different git history")
    added_skills = with_arm.overlay["skills"][len(base.overlay["skills"]):]
    overlay = [p.rstrip("/") for skill in added_skills for p in skill["paths"]]
    ancestors = {str(parent) for path in overlay for parent in PurePosixPath(path).parents} - {"."}
    rows = [r for r in with_arm.overlay["rows"][len(base.overlay["rows"]):] if r is not None]
    removed = [p for p in base.files if p not in with_arm.files]
    if removed:
        raise CaseError(f"the with-skill arm removes {removed}")
    changed = [p for p, value in base.files.items() if with_arm.files[p] != value]
    if len(changed) > 1:
        raise CaseError(f"the with-skill arm changes more than the index file: {changed}")
    for path in changed:
        old_entry, new_entry = base.files[path], with_arm.files[path]
        if not (manifest.is_file(old_entry) and manifest.is_file(new_entry)) or \
                old_entry.endswith(f" {manifest.EXEC}") != new_entry.endswith(f" {manifest.EXEC}"):
            raise CaseError(f"the with-skill arm changes the kind or executable bit of {path}")
        old = (base.path / path).read_text().split("\n")
        new = (with_arm.path / path).read_text().split("\n")
        for row in rows:
            if row in new and new.count(row) > old.count(row):
                new.remove(row)
        if new != old:
            raise CaseError(f"the with-skill arm changes {path} beyond the index row")
    extra = sorted(p for p in with_arm.files if p not in base.files)

    def allowed(path):
        if path in overlay or any(path.startswith(o + "/") for o in overlay):
            return True
        return path in ancestors and manifest.kind(with_arm.files[path]) == "dir"

    stray = [p for p in extra if not allowed(p)]
    if stray:
        raise CaseError(f"the with-skill arm adds entries outside the skill: {stray}")
    return {"without_skill": base.sha256, "with_skill": with_arm.sha256, "changed": changed, "added": extra}
