"""harnesswright's own checks (doc 12, Worlds by kind): the checks an internal skill's task case counts on, listed
in the kit part `evals/own-checks.json` (`cases.own_checks`). Each decides from the world after the run, as the
bundle holds it, written out to a scratch folder.

- `own_release_checks`: harnesswright's rule and release checks pass on the world after the run:
  `check_rules.py` and `check_release.py`, which rebuilds the release with `build.py` and compares it byte for
  byte. The scripts are the kit's: `v2/build/` at the commit the internal world kit pins (`internal.read_kit`),
  never the copies in the world, which the run may have changed. They read files the run wrote, so they run in a
  jail (`jail`): no network, the system folders read-only, the world copy the only folder they may write, and an
  environment built from nothing. A world the run left alone passes, so a clean stop passes. A script that runs
  past `LIMIT` leaves the check `undecidable`, and the judged question decides.
- `own_case_files`: every case the run wrote for `skill`, each folder under `evals/skills/<skill>/cases/`, loads
  with the harness's own case reader (`cases.Case`), so meets the whole case.json schema, and there is at least
  one. The reader only parses files, so it runs here, and it reads only what the run wrote as folders and files:
  a case folder that is, or holds, anything else, such as a link, does not load and is never followed.

A check that cannot run, such as one on a machine with no jail, raises: it stops the round and never passes.

Standard library only.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import contain
import internal
import manifest
from cases import REPO, CaseError, Case, is_name
from checks import Check, Undecidable

SCRIPTS = ("check_rules.py", "check_release.py")
LIMIT = 600  # seconds a script may run
SHOWN = 400  # characters of a failing script's output given in the reason


def write_world(bundle, out):
    """Write the world after the run, as the bundle holds it, into the empty folder `out`."""
    out = Path(out)
    for path, entry in sorted(bundle.files.items()):
        target = out / path
        if manifest.kind(entry) == "dir":
            target.mkdir(parents=True, exist_ok=True)
        elif manifest.kind(entry) == "link":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(entry.split(" ", 1)[1])
        elif manifest.is_file(entry):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.data(path))
    return out


def jail(world, kit, script):
    """Run the kit's `script` on `world` in a jail; (exit code, output)."""
    why = contain.available()
    if why:
        raise RuntimeError(f"no jail to run {script} in: {why}")
    shared = [*contain.SYSTEM, *(f"/etc/{name}" for name in contain.ETC)]  # what a host run sees of the system
    binds = [arg for folder in shared if Path(folder).exists() for arg in ("--ro-bind", folder, folder)]
    command = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", *binds, "--ro-bind", str(kit), "/kit",
               "--bind", str(world), "/world", "--tmpfs", "/tmp", "--proc", "/proc", "--dev", "/dev", "--clearenv",
               "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "LANG", "C.UTF-8", "--setenv", "HOME", "/tmp",
               "--chdir", "/world", contain.PYTHON, "-B", f"/kit/v2/build/{script}", "--root", "/world"]
    try:
        done = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=LIMIT)
    except subprocess.TimeoutExpired:
        raise Undecidable(f"{script} ran past {LIMIT} seconds, so it decided nothing") from None
    output = (done.stdout + done.stderr).strip()
    if output.startswith("bwrap:"):  # the jail failed, so the script never ran
        raise RuntimeError(f"the jail for {script} failed: {output[:SHOWN]}")
    return done.returncode, output


def own_release_checks(bundle):
    commit, _, _, _ = internal.read_kit()
    with tempfile.TemporaryDirectory() as scratch:
        kit, world = Path(scratch) / "kit", Path(scratch) / "world"
        internal.read_pinned(REPO, commit, ["v2/build"], kit)
        write_world(bundle, world)
        failed = []
        for script in SCRIPTS:
            code, output = jail(world, kit, script)
            if code != 0:
                failed.append(f"{script} exited {code}: {output[-SHOWN:]}")
            shutil.rmtree(world / "release" / "__pycache__", ignore_errors=True)
    if failed:
        return "fail", "; ".join(failed)
    return "pass", f"{' and '.join(SCRIPTS)} of the pinned kit pass on the world after the run"


def own_case_files(bundle, skill):
    root = f"evals/skills/{skill}/cases/"
    names = sorted({p[len(root):].split("/")[0] for p in bundle.files if p.startswith(root)})
    if not names:
        return "fail", f"the run wrote no case under {root}"
    with tempfile.TemporaryDirectory() as scratch:
        world = write_world(bundle, Path(scratch) / "world")
        problems = []
        for name in names:
            folder = root + name
            odd = sorted(p for p, entry in bundle.files.items() if (p == folder or p.startswith(folder + "/"))
                         and manifest.kind(entry) not in ("dir", "file"))
            if odd:  # what the reader may read is the run's folders and files only, so a link is never followed
                problems.append(f"{folder}: {odd[0]} is not a folder or a file")
                continue
            try:
                Case(world / folder, skill)
            except CaseError as error:
                problems.append(str(error))
    if problems:
        return "fail", f"{len(problems)} of {len(names)} cases under {root} do not load: {problems[0][:SHOWN]}"
    return "pass", f"all {len(names)} cases under {root} load with the harness's case reader"


CHECKS = {
    "own_release_checks": Check(own_release_checks, {},
                                about="harnesswright's rule and release checks, from the pinned kit, pass on the "
                                      "world after the run"),
    "own_case_files": Check(own_case_files, {"skill": is_name},
                            about="every case the run wrote for the skill loads with the harness's case reader"),
}
