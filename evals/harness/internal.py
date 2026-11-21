"""Build the world of an internal skill's case (doc 12, Internal worlds): harnesswright's own layout at a commit the
kit pins, without the skill under test, with the case's own files on top.

The kit part `evals/internal-world.json` holds `commit`, the pinned harnesswright commit (null until one is pinned),
`paths`, the allow list of repository paths, folders or files, `stand_in`, the name that takes the place of the
skill's words, and `left_out`, the approved list of lines the rule drops or rewrites at the pin. The reader never
reads the working tree: each path comes from the pinned commit through `git archive`, so a world never drifts.

One rule leaves the skill under test out. `evals/` is never copied, and the pinned `release/` is removed, as it is
rebuilt. Then a path that names the skill by its exact name, its folder name such as `skill-designer`
(`world.names`), points at the skill and is dropped, and so is the record of each line that names it: its template
folder, its row in `AGENTS.md`, its job row in `v2/roles.md` and its `THIRD_PARTY.md` entry all go this way, and no
file is picked by hand. A record is the line, except in a Markdown table whose header is `Field | Value`: such a
table describes the one thing its section is about, so its record is that section, with its subsections. These are
the only two shapes a record has. Every other place the world lint still finds the skill's words (`lint.names`),
such as the role `skill designer` in the rules, is a mention, not the skill: it is rewritten to the stand-in, so the
rules, the roles and the docs stay whole and agree. Only a name written as words apart, joined by `-` or `_`, or
squashed is rewritten, never words split by punctuation, as in `skill. Designer`; the lint still finds those, and a
world in which it still finds the skill is refused. Every dropped and rewritten line is listed, and the list must
equal the kit's `left_out`, the list the judges approve with the pin; any other list is refused.

The world's `release/` is then rebuilt by the world's own `v2/build/build.py`, and the world must pass that build,
`check_rules.py` and `check_release.py` before any case touches it: a world that does not is refused. Then the
case's `world/` folder is copied on top, its `internal_world.jobs` rows are added to the Jobs table of
`v2/roles.md`, and the world is rebuilt and checked again by the same rule, so a skill the case brings is built as a
skill that went through a round is, and a skill in no job is refused by that build. Last, the case's
`internal_world.remove` paths, each inside the allow list and in the built world, are removed, after the build, so
the build never puts back what the case takes away. The world's instructions are its own files: `docs/design` comes
in through the allow list like any other path. Every file it needs must be in it, so a world in which a Markdown
link or a `@` import leads to a path the world lacks is refused, before and after the case's files are added.

One rule decides what a case writes. The pinned build owns its code, the folder of the `BUILD` scripts and all they
run, and the `release/` it makes (`BUILT_BY_PIN`); the case may write every other path. So the case's `world/` may
hold no path at, inside or above one of them but a folder, and the build that runs is always the pinned one. What
the case writes is its own (`own_files`), never the approved base: each path of its `world/`, and every other path
whose entry differs from the base's, changed through its jobs rows or the release rebuilt from them. So only a base
file the case left byte for byte unchanged is approved base text (`lint.visible`).

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
BUILT_BY_PIN = (*sorted({str(PurePosixPath(p).parent) for p in BUILD}), RELEASE)  # never the case's to write
COMMIT = re.compile(r"[0-9a-f]{40}")


def read_kit(path=None):
    """(commit, paths, stand_in, left_out) from the kit part. CaseError when it is missing, unsound or pins no commit."""
    path = Path(path or KIT_FILE)
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaseError(f"{path.name}: {error}") from None
    paths = data.get("paths") if isinstance(data, dict) else None
    if not (isinstance(paths, list) and paths and all(is_path(p) for p in paths) and len(set(paths)) == len(paths)
            and is_text(data.get("stand_in", "")) and isinstance(data.get("left_out"), list)
            and set(data) == {"commit", "paths", "stand_in", "left_out"}):
        raise CaseError(f"{path.name}: must be {{commit, paths, stand_in, left_out}}: a commit, a list of repository "
                        "paths, a name and the approved list of left-out lines")
    if not (isinstance(data["commit"], str) and COMMIT.fullmatch(data["commit"])):
        raise CaseError(f"{path.name}: no commit is pinned, so no internal world can be built")
    return data["commit"], paths, data["stand_in"], data["left_out"]


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
    """`text` with each of the skill's words, in any case, written apart, joined by `-` or `_`, or squashed, replaced
    by the stand-in written the same way, plural kept. Words split by any other character are left alone."""
    words = _words(skill)
    pattern = re.compile(r"(?<![A-Za-z0-9])" + r"([ \t]+|[-_]?)".join(map(re.escape, words)) + r"(s?)(?![A-Za-z0-9])",
                         re.IGNORECASE)

    def written(match):
        found, gap = match.group(0), (match.group(1) if len(words) > 1 else " ")
        new = re.findall(r"[a-z0-9]+", stand_in.casefold())
        if gap == "" and len(words) > 1:  # squashed, as in `SkillDesigner`
            new = [w.capitalize() if found[0].isupper() else w for w in new]
        text = gap.join(new) if gap else "".join(new)
        return (text[0].upper() + text[1:] if found[0].isupper() else text) + match.group(match.lastindex)

    return pattern.sub(written, text)


HEADING = re.compile(r"(#{1,6})[ \t]")
FENCE = re.compile(r"[ \t]*(```|~~~)")


def _cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _records(lines, hits, markdown):
    """The line numbers (from 0) that `hits`, the lines naming the skill, drop: each one's record."""
    drop = set(hits)
    if not markdown:
        return drop
    fenced, heads = False, []  # (line, level) of each heading outside a code fence
    for n, line in enumerate(lines):
        fenced = fenced != bool(FENCE.match(line))
        found = None if fenced else HEADING.match(line)
        if found:
            heads.append((n, len(found.group(1))))
    for hit in hits:
        start = hit
        while start > 0 and lines[start - 1].lstrip().startswith("|"):
            start -= 1
        if not (lines[hit].lstrip().startswith("|") and _cells(lines[start]) == ["Field", "Value"]):
            continue
        owner = [(n, level) for n, level in heads if n < hit]
        if owner:
            top, level = owner[-1]
            end = next((n for n, lv in heads if n > top and lv <= level), len(lines))
            drop.update(range(top, end))
    return drop


def leave_out(folder, skill, stand_in):
    """Apply the one rule of the module to `folder`, and return what it did: [path, None, None, None] for each
    dropped path, and [path, line number, line, new line or None] for each rewritten or dropped line. CaseError when
    the lint still finds the skill."""
    import lint  # the world lint decides what names the skill; imported here, as it imports the world builder
    import world
    exact, done = world.names([skill]), []
    for path in sorted(manifest.manifest(folder), reverse=True):  # files before the folders that hold them
        target = Path(folder) / path
        if exact.search(path):
            shutil.rmtree(target) if target.is_dir() and not target.is_symlink() else target.unlink()
            done.append([path, None, None, None])
            continue
        if not target.is_file() or target.is_symlink():
            continue
        try:
            text = target.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            raise CaseError(f"{path}: not UTF-8 text, so the lint cannot read it") from None
        lines = text.splitlines(keepends=True)
        drop = _records(lines, [n for n, line in enumerate(lines) if exact.search(line)], path.endswith(".md"))
        kept = []
        for n, line in enumerate(lines):
            new = None if n in drop else _rename(line, skill, stand_in)
            if new != line:
                done.append([path, n + 1, line.rstrip("\r\n"), None if new is None else new.rstrip("\r\n")])
            if new is not None:
                kept.append(new)
        kept = "".join(kept)
        if kept != text:
            target.write_bytes(kept.encode("utf-8"))
        if lint.names(lint.Place(path, f"{path}\n{kept}", "world"), skill):
            raise CaseError(f"{path}: the lint still finds {skill} after the rule leaves it out")
    return sorted(done, key=lambda row: (row[0], row[1] or 0))


LINK = re.compile(r"\]\(<?([^)<>\s]+)>?(?:[ \t]+\"[^\"]*\")?\)")
IMPORT = re.compile(r"^@(\S+)[ \t]*$", re.MULTILINE)
SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")


def check_links(folder):
    """Refuse a world in which a Markdown file's relative link, or a `@` import, leads to a path the world lacks: the
    world's files are its instructions, and every file they need must be in it."""
    built, missing = manifest.manifest(folder), []
    for path in sorted(p for p, e in built.items() if p.endswith(".md") and manifest.kind(e) == "file"):
        text = (Path(folder) / path).read_bytes().decode("utf-8", "replace")
        for found in [*LINK.findall(text), *IMPORT.findall(text)]:
            target = found.split("#", 1)[0]
            if not target or SCHEME.match(target):
                continue
            rel = os.path.normpath(os.path.join(os.path.dirname(path), target.rstrip("/")))
            if rel not in built:
                missing.append(f"{path} -> {found}")
    if missing:
        raise CaseError(f"the internal world names files it lacks: {'; '.join(missing)}")


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
    commit, paths, stand_in, approved = read_kit(kit)
    read_pinned(repo, commit, paths, out)
    shutil.rmtree(Path(out) / RELEASE, ignore_errors=True)  # rebuilt below from the world's own sources
    done = leave_out(out, skill, stand_in)
    if done != approved:
        first = next(n for n in range(len(done) + 1) if done[n:n + 1] != approved[n:n + 1])
        raise CaseError(f"the lines left out of the internal world are not the kit's approved `left_out` list: "
                        f"{len(done)} found, {len(approved)} approved, first difference at entry {first}: found "
                        f"{done[first:first + 1]}, approved {approved[first:first + 1]}")
    build_checks(out)
    check_links(out)
    return Path(out)


def world_of(case, out, repo=REPO, kit=None):
    """The world `case` runs in, written into the empty folder `out`: the internal world of its skill with the
    case's `world/` folder on top and its `jobs` rows added, rebuilt and checked, less its `remove` paths. When the
    sources the case leaves still build, the release is rebuilt from them, so it is what the build makes of the world
    and passes the release check before any run; a `remove` path that build puts back is refused. When they do not
    build, such as with `v2/VERSION` removed, the release stays as built before the remove. It sets the case's
    `own_files` ({path: "world" for a path of its `world/`, or "derived" for any other path it changed})."""
    _, paths, _, _ = read_kit(kit)
    base(case.skill, out, repo, kit)
    before = manifest.manifest(out)
    for path, entry in sorted(case.world_files.items()):  # the one rule: the pinned build's paths are never the case's
        owned = [p for p in BUILT_BY_PIN if path == p or p.startswith(f"{path}/") and manifest.kind(entry) != "dir"
                 or path.startswith(f"{p}/")]
        if owned:
            raise CaseError(f"{case.id}: world/{path}: the pinned build owns {owned[0]}, so a case never writes it")
    if (case.folder / "world").is_dir():  # a case may add no file (`cases.Case`)
        shutil.copytree(case.folder / "world", out, symlinks=True, dirs_exist_ok=True)
    add_jobs(out, case.internal_world.get("jobs", []), case.id)
    try:
        build_checks(out)
    except CaseError as error:
        raise CaseError(f"{case.id}: the world with the case's files fails its build: {error}") from None
    built = manifest.manifest(out)
    for path in case.internal_world["remove"]:
        inside = any(path == p or PurePosixPath(p) in PurePosixPath(path).parents for p in paths)
        if not inside or path not in built:
            raise CaseError(f"{case.id}: remove {path}: not an allow-listed path of the built world")
        target = Path(out) / path
        shutil.rmtree(target) if target.is_dir() and not target.is_symlink() else target.unlink()
    if case.internal_world["remove"]:
        _rebuild(case, out)
    check_links(out)
    case.own_files = {path: "world" if path in case.world_files else "derived"  # the base is what it left alone
                      for path, entry in manifest.manifest(out).items()
                      if path in case.world_files or before.get(path) != entry}
    return Path(out)


def _rebuild(case, out):
    """Rebuild the release of the world at `out` from the sources it holds after the case's `remove`, in a copy, and
    take it when that build and its checks pass. CaseError when it puts a removed path back."""
    with tempfile.TemporaryDirectory(prefix="hw-rebuild-") as scratch:
        trial = Path(scratch) / "world"
        shutil.copytree(out, trial, symlinks=True)
        try:
            build_checks(trial)
        except CaseError:
            return  # the sources left do not build, so the release stays as built before the remove
        back = [path for path in case.internal_world["remove"] if (trial / path).exists()]
        if back:
            raise CaseError(f"{case.id}: remove {', '.join(back)}: the build puts it back; remove its source too")
        shutil.rmtree(Path(out) / RELEASE)
        shutil.copytree(trial / RELEASE, Path(out) / RELEASE, symlinks=True)


def add_jobs(folder, rows, name):
    """Add `rows` after the last row of the Jobs table of `folder`'s `v2/roles.md`. CaseError when it has none."""
    if not rows:
        return
    path = Path(folder) / ROLES
    lines = path.read_text(encoding="utf-8").split("\n") if path.is_file() else []
    try:
        head = lines.index(JOBS_HEADER)
    except ValueError:
        raise CaseError(f"{name}: jobs: {ROLES} has no Jobs table to add rows to") from None
    end = head + 1
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    path.write_text("\n".join(lines[:end] + list(rows) + lines[end:]), encoding="utf-8")


ROLES = "v2/roles.md"
JOBS_HEADER = "| Job | Roles | Skills in order | `rest` skill |"
_BUILT = {}  # case folder -> (its built world, its own files), kept for the life of the process: one per case


def resolve(case):
    """Point `case.world` at its built internal world, once per case per process. Old cases keep their world."""
    if case.internal_world is None:
        return case
    key = str(case.folder.resolve())
    if key not in _BUILT:
        folder = tempfile.mkdtemp(prefix="hw-internal-")
        atexit.register(shutil.rmtree, folder, True)
        try:
            _BUILT[key] = world_of(case, Path(folder) / "world", REPO, KIT_FILE), case.own_files
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
    case.world, case.own_files = _BUILT[key]
    return case
