"""Build the world of an internal skill's case (doc 12, Internal worlds): harnesswright's own layout at a commit the
kit pins, without the skill under test, with the case's own files on top.

The kit part `evals/internal-world.json` holds `commit`, the pinned harnesswright commit (null until one is pinned),
`paths`, the allow list of repository paths, folders or files, and `stand_in`, the name that takes the place of the
skill's words. The reader never reads the working tree: each path comes from the pinned commit through `git
archive`, so a world never drifts.

One rule leaves the skill under test out. `evals/` is never copied. Then a file or line that names the skill by its
exact name, its folder name such as `skill-designer` (`world.names`), points at the skill and is dropped: its
template folder, its release copy, its row in `AGENTS.md` and its job row in `v2/roles.md` all go this way, and
no file is picked by hand. Every other place the world lint still finds the skill's words (`lint.names`), such as
the role `skill designer` in the rules and the roles file, is a mention, not the skill: it is rewritten to the
stand-in, so the rules, the roles and the docs stay whole and agree. Dropping those files would take the rules
the skill applies out of its own world. A world in which the lint still finds the skill is refused.

The world's `release/` is then rebuilt by the world's own `v2/build/build.py`, and the world must pass that build,
`check_rules.py` and `check_release.py` before any case touches it: a world that does not is refused. Last, the
case's `internal_world.remove` paths, each inside the allow list and in the built world, are removed, and the
case's `world/` folder is copied on top.

Standard library only.
"""

import atexit
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

import manifest
from cases import REPO, CaseError, is_path, is_text

KIT_FILE = REPO / "evals" / "internal-world.json"
LEFT_OUT = "evals"  # the measuring kit and every case: never part of a world
BUILD = ("v2/build/build.py", "v2/build/check_rules.py", "v2/build/check_release.py")
RELEASE = "release"
COMMIT = re.compile(r"[0-9a-f]{40}")


def read_kit(path=None):
    """(commit, paths, stand_in) from the kit part. CaseError when it is missing, unsound or pins no commit."""
    path = Path(path or KIT_FILE)
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaseError(f"{path.name}: {error}") from None
    paths = data.get("paths") if isinstance(data, dict) else None
    if not (isinstance(paths, list) and paths and all(is_path(p) for p in paths) and len(set(paths)) == len(paths)
            and is_text(data.get("stand_in", "")) and set(data) == {"commit", "paths", "stand_in"}):
        raise CaseError(f"{path.name}: must be {{commit, paths, stand_in}}: a commit, a list of repository paths "
                        "and a name")
    if not (isinstance(data["commit"], str) and COMMIT.fullmatch(data["commit"])):
        raise CaseError(f"{path.name}: no commit is pinned, so no internal world can be built")
    return data["commit"], paths, data["stand_in"]


def _run(args, cwd, what):
    """Run a command with a plain environment. CaseError, with its output, when it fails."""
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
    env.update(HOME=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    try:
        return subprocess.run(args, cwd=cwd, env=env, check=True, capture_output=True, timeout=600).stdout
    except subprocess.CalledProcessError as error:
        output = (error.stderr or error.stdout or b"").decode("utf-8", "replace").strip()
        raise CaseError(f"{what} failed: {output}") from None
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CaseError(f"{what} could not run: {error}") from None


def read_pinned(repo, commit, paths, out):
    """Write the allow-listed `paths` of `repo` at `commit` into the empty folder `out`, from git, never the
    working tree. `evals/` is never written."""
    data = _run(["git", "-C", str(repo), "archive", "--format=tar", commit, "--", *paths], repo, "git archive")
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(out, filter="data")  # no path outside `out`, no device, no link that leads out
    shutil.rmtree(Path(out) / LEFT_OUT, ignore_errors=True)


def _words(skill):
    return re.findall(r"[a-z0-9]+", skill)


def _rename(text, skill, stand_in):
    """`text` with each of the skill's words, as the lint reads them in any case and with any separator or none,
    replaced by the stand-in written the same way, plural kept."""
    words = _words(skill)
    pattern = re.compile(r"(?<![A-Za-z0-9])" + r"([^A-Za-z0-9]*)".join(map(re.escape, words)) + r"(s?)(?![A-Za-z0-9])",
                         re.IGNORECASE)

    def written(match):
        found, gap = match.group(0), (match.group(1) if len(words) > 1 else " ")
        new = re.findall(r"[a-z0-9]+", stand_in.casefold())
        if gap == "" and len(words) > 1:  # squashed, as in `SkillDesigner`
            new = [w.capitalize() if found[0].isupper() else w for w in new]
        text = gap.join(new) if gap else "".join(new)
        return (text[0].upper() + text[1:] if found[0].isupper() else text) + match.group(match.lastindex)

    return pattern.sub(written, text)


def leave_out(folder, skill, stand_in):
    """Apply the one rule of the module to `folder`. CaseError when the lint still finds the skill."""
    import lint  # the world lint decides what names the skill; imported here, as it imports the world builder
    import world
    exact = world.names([skill])
    for path in sorted(manifest.manifest(folder), reverse=True):  # files before the folders that hold them
        target = Path(folder) / path
        if exact.search(path):
            shutil.rmtree(target) if target.is_dir() and not target.is_symlink() else target.unlink()
            continue
        if not target.is_file() or target.is_symlink():
            continue
        try:
            text = target.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            raise CaseError(f"{path}: not UTF-8 text, so the lint cannot read it") from None
        lines = text.splitlines(keepends=True)
        kept = "".join(_rename(line, skill, stand_in) for line in lines if not exact.search(line))
        if kept != text:
            target.write_bytes(kept.encode("utf-8"))
        if lint.names(lint.Place(path, f"{path}\n{kept}", "world"), skill):
            raise CaseError(f"{path}: the lint still finds {skill} after the rule leaves it out")


def build_checks(folder):
    """Rebuild `folder`'s release with its own build, then run its rule and release checks. CaseError on a fault."""
    missing = [p for p in BUILD if not (Path(folder) / p).is_file()]
    if missing:
        raise CaseError(f"the internal world has no {', '.join(missing)}")
    shutil.rmtree(Path(folder) / RELEASE, ignore_errors=True)
    for script in BUILD:
        _run([sys.executable, "-B", script], folder, f"the internal world's {script}")


def base(skill, out, repo=REPO, kit=None):
    """The internal world of `skill`, without any case, written into the empty folder `out`."""
    commit, paths, stand_in = read_kit(kit)
    read_pinned(repo, commit, paths, out)
    leave_out(out, skill, stand_in)
    build_checks(out)
    return Path(out)


def world_of(case, out, repo=REPO, kit=None):
    """The world `case` runs in, written into the empty folder `out`: the internal world of its skill, less the
    case's `remove` paths, with the case's `world/` folder on top."""
    _, paths, _ = read_kit(kit)
    base(case.skill, out, repo, kit)
    built = manifest.manifest(out)
    for path in case.internal_world["remove"]:
        inside = any(path == p or PurePosixPath(p) in PurePosixPath(path).parents for p in paths)
        if not inside or path not in built:
            raise CaseError(f"{case.id}: remove {path}: not an allow-listed path of the built world")
        target = Path(out) / path
        shutil.rmtree(target) if target.is_dir() and not target.is_symlink() else target.unlink()
    shutil.copytree(case.folder / "world", out, symlinks=True, dirs_exist_ok=True)
    return Path(out)


_BUILT = {}  # case folder -> its built world, kept for the life of the process, so each arm reads the same one


def resolve(case):
    """Point `case.world` at its built internal world, once per case per process. Old cases keep their world."""
    if case.internal_world is None:
        return case
    key = str(case.folder.resolve())
    if key not in _BUILT:
        folder = tempfile.mkdtemp(prefix="hw-internal-")
        atexit.register(shutil.rmtree, folder, True)
        try:
            _BUILT[key] = world_of(case, Path(folder) / "world", REPO, KIT_FILE)
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
    case.world = _BUILT[key]
    return case
