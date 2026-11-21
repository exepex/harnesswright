"""What a case's texts state about its world (doc 11, World lint): a value a case states is one the built world gives,
so a re-pin of an internal world, or any change to a world, cannot leave a case stating the old value.

One rule, read from the built without-skill arm. A case text is its prompt and every text of its expectations
(`cited.expectation_texts`). In it:

- a version (`x.y.z`), in a world that holds `v2/VERSION`, is that version or one raise of it (its last, middle or
  first number), the only versions a run of harnesswright's own world can start from or reach;
- a commit hash (7 to 40 hex digits, with a digit and a letter) is a commit of the built history, or a value a
  file of the built world spells, such as a label's commit in a world with no history.
- a line of a world file is never named by its number (`path:N`): a number cannot be checked against what the
  line says, and it moves when the world does. A case names the section, or cites the line as a contract source,
  whose quote the lint finds where it is cited (`cited.citations`).

Each allowed value is taken from the built world, never written here. Standard library only.
"""

import re

import world
from cases import CaseError
from cited import expectation_texts

VERSION = re.compile(r"(?<![\w.])\d+\.\d+\.\d+(?!\w|\.\d)")
LINE = re.compile(r"(?<![\w./-])([\w.-]+(?:/[\w.-]+)*):(\d+)(?!\d)")
HASH = re.compile(r"(?<![0-9A-Za-z])(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}(?![0-9A-Za-z])")


def raises(version):
    """`version` and each version one raise of it reaches."""
    major, minor, patch = map(int, version.split("."))
    return {version, f"{major}.{minor}.{patch + 1}", f"{major}.{minor + 1}.0", f"{major + 1}.0.0"}


def case_texts(case):
    return [case.prompt or ""] + [text for e in case.expectations for text in expectation_texts(e)]


def check(case, arm):
    """The problems of `case`'s texts against its built without-skill arm `arm`: each value stated that the built
    world does not give."""
    root, problems = arm.path, []
    texts = case_texts(case)
    version_file = root / "v2" / "VERSION"
    if version_file.is_file():
        start = version_file.read_text(encoding="utf-8").strip()
        allowed = raises(start)
        problems += [f"states version {v!r}, but the built world's v2/VERSION is {start!r} and a run reaches only "
                     f"{sorted(allowed)}" for v in sorted({v for t in texts for v in VERSION.findall(t)})
                     if v not in allowed]
    lines = sorted({m for t in texts for m in LINE.findall(t)})
    problems += [f"names line {n} of the world file {path} by its number; name its section or cite it as a contract "
                 "source" for path, n in lines if ".." not in path.split("/") and (root / path).is_file()]
    stated = sorted({h for t in texts for h in HASH.findall(t)})
    if stated:
        try:
            commits = world._git(root, "log", "--all", "--format=%H").split() if (root / ".git").is_dir() else []
        except CaseError:
            commits = []
        spelled = "".join(_text(path) for path in sorted(root.rglob("*"))
                          if path.is_file() and ".git" not in path.relative_to(root).parts)
        problems += [f"states commit {h!r}, which is no commit of the built history and no value a world file spells"
                     for h in stated if not any(c.startswith(h) for c in commits) and h not in spelled]
    return problems


def _text(path):
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""
