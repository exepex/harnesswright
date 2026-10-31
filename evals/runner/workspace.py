"""Disposable task and trigger workspaces for the eval runner.

Python 3 standard library only.
"""

import shutil
import tempfile
from pathlib import Path

# Project folders where known hosts discover skills, and `skills/`, where this repository keeps its skill
# sources. A copied base folder may hold the skill under test in any of them, which would leak it into a
# baseline run or mix it with the installed copy.
SKILL_FOLDERS = ("skills", ".claude/skills", ".agents/skills", ".opencode/skills", ".goose/skills")


def _copy_ignore(excluded):
    """copytree ignore function: skip .git and every path in `excluded` (resolved paths)."""
    excluded = {Path(p).resolve() for p in excluded}

    def ignore(folder, names):
        here = Path(folder).resolve()
        return {n for n in names if n == ".git" or (here / n).resolve() in excluded}
    return ignore


def make_workspace(adapter, skill_path, skill_name, skill_text=None, base=None, exclude=()):
    """Create a disposable workspace, copy `base` into it (without `exclude`) and install the skill.

    Any copy of the skill that came with `base` is removed first, so a baseline run never sees it. A with-skill
    run gets the skill under test in the host's skills folder and in each folder where `base` held it, so
    paths in the base that name the skill, such as an index in AGENTS.md, still resolve.
    """
    workspace = Path(tempfile.mkdtemp(prefix="hw-eval-"))
    if base is not None:
        shutil.copytree(base, workspace, dirs_exist_ok=True, ignore=_copy_ignore(exclude))
    held = [workspace / folder / skill_name for folder in SKILL_FOLDERS
            if (workspace / folder / skill_name).is_dir()]
    remove_skill(adapter, workspace, skill_name)
    if skill_path is not None:
        for target in [adapter.skill_dir(workspace, skill_name)] + held:
            shutil.copytree(skill_path, target, dirs_exist_ok=True)
            if skill_text is not None:
                (target / "SKILL.md").write_text(skill_text, encoding="utf-8")
    return workspace


def remove_skill(adapter, workspace, skill_name):
    """Remove every copy of the skill from the workspace: each of SKILL_FOLDERS and the host's skills folder."""
    for folder in SKILL_FOLDERS:
        shutil.rmtree(Path(workspace) / folder / skill_name, ignore_errors=True)
    shutil.rmtree(adapter.skill_dir(workspace, skill_name), ignore_errors=True)
