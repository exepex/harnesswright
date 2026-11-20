"""Team notes hold the team's rules, never harnesswright's (doc 12, Team worlds; doc 07).

A team world is a team repository: its code, its tests, its `.harness/` folder (profile and stories, which the
skills read) and its own notes. One rule, read by the world lint for each world file of a `team` skill's case:
harnesswright's rules may appear only where the allow list says, `ALLOWED`, the team's `.harness/` folder, whose
profile names the rules it waives or binds. Anywhere else, a world file may hold no rule ID the release defines and
no run of `textruns.RUN` words of the release's rule text. The release, `release/rules/` at the repository, is the
one source of both, so a rule added later counts without being listed.

Standard library only.
"""

import re
from pathlib import Path

from textruns import RUN, all_runs, runs

ALLOWED = (".harness/",)  # the one place a team world may name harnesswright's rules
RULES = ("release", "rules")
HEADING = re.compile(r"^#{2,4} ([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+) · ", re.MULTILINE)


def harness_rules(repo):
    """(rule IDs, runs of rule text) of the release at `repo`: every rule file of every layer folder it ships."""
    texts = [path.read_text(encoding="utf-8", errors="replace")
             for path in sorted(Path(repo).joinpath(*RULES).glob("*/*.md"))]
    ids = {found for text in texts for found in HEADING.findall(text)}
    return ids, all_runs(texts, {RUN})


def found(path, text, rules):
    """The problems of one world file, `path` with `text`, against `rules` from `harness_rules`."""
    if path.startswith(ALLOWED):
        return []
    ids, text_runs = rules
    named = sorted(i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", text))
    hits = sorted(text_runs & runs(text, {RUN}))
    return ([f"{path}: names harnesswright's rule {named[0]}; a team's notes hold its own rules"] if named else []) + \
        ([f"{path}: holds harnesswright's rule text, such as {hits[0]!r}"] if hits else [])
