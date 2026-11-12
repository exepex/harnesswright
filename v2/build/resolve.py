"""The standards reader's command: resolve an application's rule layers (plan/b01-plan.md part e).

Standard library only. Shipped in each release skill's scripts/ beside rulebook.py, reach.py and copyform.py, and
imports only them. One rule governs it, as it does rulebook.py: every line and value it reads has a shape listed
here, and anything else stops the run naming the file and line (HW-AG-09). Part e1a reads and checks the inputs of
docs/design/03-standards.md "Resolving the rules for an application" and docs/design/07-repo-profile.md, starting
here with the profile and layer.yaml; parts e1b and e2 combine them and write rules.md and the rules texts.

Run: python3 resolve.py --repo REPO --run RUN-ID --date YYYY-MM-DD
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import rulebook
from rulebook import DP_ID, RULE_ID, RulebookError, fail

PROFILE = ".harness/profile.yaml"
MAX_LIMIT = 60000
DEFAULT_LIMIT = 30000
READ = ("harnesswright", "standards", "waivers", "rules-text-limit", "decisions")  # every other section is skipped
VALUE = re.compile(r"[\x20-\x7e\xa0-\ufffd]+")
SHAPES = {
    "version": re.compile(r"[0-9]+\.[0-9]+\.[0-9]+"),
    "folder": re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*/?"),
    "name": re.compile(r"[a-z][a-z0-9]*"),
    "language": re.compile(r"[a-z][a-z0-9]*(?:-[a-z][a-z0-9]*)*"),
    "rule": re.compile(rf"{RULE_ID.pattern}|{DP_ID.pattern}"),
    "until": rulebook.DATE,
    "reason": VALUE,
    "approved by": re.compile(r"[A-Za-z0-9._-]+(?:, [A-Za-z0-9._-]+)*"),
    "owner": VALUE,
    "limit": re.compile(r"[1-9][0-9]*"),
    "key": re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*"),
    "option": re.compile(r"[a-z0-9-]+"),
}
LINE = re.compile(r"( *)(- )?([a-z][a-z -]*[a-z]|[a-z]):(?: (\S.*))?")
COMMENT = re.compile(r"\s+#\s.*$")


class ResolveError(RulebookError):
    """An input that stops the run, named with its file and line or its layer."""


def unquote(value):
    if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def depth(line):
    return len(line) - len(line.lstrip(" "))


def parse(path, lines, indent):
    """A block of (number, line) pairs at one indent into a dict of (number, value) leaves, or a list of such dicts.
    A line is `key: value`, `key:` with a deeper block under it, or `- key: value` starting a list item."""
    if lines[0][1][indent:].startswith("- "):
        starts = [i for i, (_, line) in enumerate(lines) if depth(line) == indent] + [len(lines)]
        items = []
        for here, after in zip(starts, starts[1:]):
            number, line = lines[here]
            if not line[indent:].startswith("- "):
                fail(path, number, "a block mixes list items and keys")
            items.append(parse(path, [(number, " " * (indent + 2) + line[indent + 2:])] + lines[here + 1:after],
                               indent + 2))
        return items
    data, index = {}, 0
    while index < len(lines):
        number, line = lines[index]
        found = LINE.fullmatch(line)
        if not found or found.group(2) or len(found.group(1)) != indent:
            fail(path, number, f"line has no allowed shape here: {line!r}")
        key, value = found.group(3), found.group(4)
        if key in data:
            fail(path, number, f"{key!r} appears twice")
        after = next((i for i in range(index + 1, len(lines)) if depth(lines[i][1]) <= indent), len(lines))
        if value is not None and after > index + 1:
            fail(path, lines[index + 1][0], f"line has no allowed shape here: {lines[index + 1][1]!r}")
        if value is None and after == index + 1:
            fail(path, number, f"{key!r} has no value")
        data[key] = (number, value) if value is not None else parse(path, lines[index + 1:after], indent + 2)
        index = after
    return data


def read_yaml(path, read):
    """The top-level sections named in read (all of them when read is None), parsed; every other section is
    skipped as an unread block."""
    lines = [(i + 1, COMMENT.sub("", line)) for i, line in enumerate(rulebook.read_lines(path))]
    lines = [(n, line) for n, line in lines if line.strip() and not line.lstrip().startswith("#")]
    tops = [i for i, (_, line) in enumerate(lines) if not line.startswith(" ")] + [len(lines)]
    data = {}
    for here, after in zip(tops, tops[1:]):
        number, line = lines[here]
        found = LINE.fullmatch(line)
        if not found or found.group(2):
            fail(path, number, f"top-level line has no allowed shape: {line!r}")
        key, value = found.group(3), found.group(4)
        if key in data:
            fail(path, number, f"{key!r} appears twice")
        if read is None or key in read:
            if value is None and after == here + 1:
                fail(path, number, f"{key!r} has no value")
            data[key] = (number, value) if value is not None else parse(path, lines[here + 1:after], 2)
    return data


def leaf(path, node, shape, where):
    """One value: a (number, text) leaf whose unquoted text has the named shape."""
    if not isinstance(node, tuple):
        fail(path, where, f"expected one {shape} value")
    number, text = node
    value = unquote(text)
    if not SHAPES[shape].fullmatch(value):
        fail(path, number, f"{value!r} is not an allowed {shape}")
    return value


def keys(path, node, required, optional, where):
    """A dict holding every required key and no key outside required and optional."""
    if not isinstance(node, dict):
        fail(path, where, f"expected keys {', '.join(required + optional)}")
    missing = [k for k in required if k not in node]
    extra = [k for k in node if k not in required + optional]
    if missing or extra:
        fail(path, where, f"missing {missing} or not allowed {extra}; allowed: {', '.join(required + optional)}")
    return node


def items(path, node, where):
    if not isinstance(node, list):
        fail(path, where, "expected a list of `- key: value` items")
    return node


def line_of(node):
    return node[0] if isinstance(node, tuple) else 0


def read_profile(path):
    """The sections of .harness/profile.yaml that resolve reads, checked against their allowed shapes."""
    data = keys(path, read_yaml(path, READ), ["harnesswright"], [k for k in READ if k != "harnesswright"], 1)
    install = keys(path, data["harnesswright"], ["version", "folder"], [], 1)
    profile = {"version": leaf(path, install["version"], "version", 1),
               "folder": leaf(path, install["folder"], "folder", 1), "languages": [], "layers": [],
               "repository": None, "waivers": [], "limit": DEFAULT_LIMIT, "decisions": {}}
    standards = keys(path, data.get("standards", {}), [], ["languages", "layers", "repository"], 1)
    if "languages" in standards:
        number, text = standards["languages"] if isinstance(standards["languages"], tuple) else (1, "")
        if not (text.startswith("[") and text.endswith("]")):
            fail(path, number, "languages is a list written as [a, b]")
        names = [n.strip() for n in text[1:-1].split(",")] if text[1:-1].strip() else []
        profile["languages"] = [leaf(path, (number, n), "language", number) for n in names]
    for item in items(path, standards.get("layers", []), 1):
        layer = keys(path, item, ["name", "folder", "version"], [], line_of(next(iter(item.values()))))
        profile["layers"].append({k: leaf(path, layer[k], k, 1) for k in ("name", "folder", "version")})
    if "repository" in standards:
        profile["repository"] = leaf(path, standards["repository"], "folder", 1)
    for item in items(path, data.get("waivers", []), 1):
        number = line_of(next(iter(item.values())))
        waiver = keys(path, item, ["rule", "reason", "until", "approved by"], [], number)
        profile["waivers"].append({**{k: leaf(path, waiver[k], k, number) for k in waiver}, "line": number})
    if "rules-text-limit" in data:
        number = line_of(data["rules-text-limit"])
        profile["limit"] = int(leaf(path, data["rules-text-limit"], "limit", number))
        if profile["limit"] > MAX_LIMIT:
            fail(path, number, f"rules-text-limit {profile['limit']} is over the maximum of {MAX_LIMIT}")
    decisions = keys(path, data.get("decisions", {}), [], list(data.get("decisions", {})), 1)
    for key, node in decisions.items():
        profile["decisions"][leaf(path, (line_of(node), key), "key", 1)] = (leaf(path, node, "option", 1),
                                                                             line_of(node))
    return profile


def read_layer_yaml(name, folder, version, files):
    """The owner of a layer 3 to 5 folder, after checking its layer.yaml and its version against the profile."""
    path = folder / "layer.yaml"
    if not path.is_file():
        raise ResolveError(f"layer {name}: {path} is missing or cannot be read")
    files.append(path)
    data = keys(path, read_yaml(path, None), ["owner", "version"], [], 1)
    found = leaf(path, data["version"], "version", 1)
    if found != version:
        raise ResolveError(f"layer {name} ({folder}): version {found} is not the profile's {version}")
    return leaf(path, data["owner"], "owner", 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    args = parser.parse_args(argv)
    try:
        read_profile(Path(args.repo) / PROFILE)
    except RulebookError as error:
        print(f"resolve stopped: {error}", file=sys.stderr)
        return 1
    print("resolve: profile read; the layers are not read yet (B0.1 part e1a, second pull request)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
