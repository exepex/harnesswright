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
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import rulebook
from rulebook import DP_ID, RULE_ID, RulebookError, fail

PROFILE = ".harness/profile.yaml"
MAX_LIMIT = 60000
DEFAULT_LIMIT = 30000
READ = ("harnesswright", "standards", "waivers", "rules-text-limit", "decisions")
SKIP = ("toolchain", "scripts", "models", "capabilities", "process")  # doc 07's sections that resolve does not read
VALUE = re.compile(f"{rulebook.PRINTABLE}+")
ACCOUNT = r"[A-Za-z0-9._-]+"
SHAPES = {
    "version": re.compile(r"[0-9]+\.[0-9]+\.[0-9]+"),
    "folder": re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*/?"),
    "name": re.compile(r"[a-z][a-z0-9]*"),
    "language": re.compile(r"[a-z][a-z0-9]*(?:-[a-z][a-z0-9]*)*"),
    "rule": re.compile(rf"{RULE_ID.pattern}|{DP_ID.pattern}"),
    "until": rulebook.DATE,
    "reason": VALUE,
    "approved by": re.compile(rf"{ACCOUNT}(?:, ?{ACCOUNT})*"),
    "owner": VALUE,
    "limit": re.compile(r"[1-9][0-9]*"),
    "key": re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*"),
    "option": re.compile(r"[a-z0-9-]+"),
}
LINE = re.compile(r"( *)(- )?(?:([a-z][a-z0-9 -]*[a-z0-9]|[a-z]):(?: +(.*))?|(.+))")  # key: value, or - item
COMMENT = re.compile(r"(?:^|\s)#")
QUOTED_END = re.compile(r"\s*|\s+#.*")


class ResolveError(RulebookError):
    """An input that stops the run, named with its file and line or its layer."""


@dataclass
class Node:
    """One parsed value and the line it starts on: text, a list of Nodes, or a dict of key to Node."""
    line: int
    value: object


def read_file(path, label=""):
    """The file's lines; a file that is missing or cannot be read stops the run naming it."""
    try:
        return rulebook.read_lines(path)
    except (OSError, UnicodeDecodeError) as error:
        raise ResolveError(f"{label}{path}: is missing or cannot be read ({type(error).__name__})") from None


def scalar(path, number, raw):
    """A value's text: quoted text in full, or the text before a ` #` comment. `[]`, `{}` and `[a, b]` give a list
    or dict. None when the line has no value."""
    if raw and raw[0] in "\"'":
        end = raw.find(raw[0], 1)
        if end < 0 or not QUOTED_END.fullmatch(raw[end + 1:]):
            fail(path, number, "a quoted value must end with its quote, then nothing or a comment")
        return raw[1:end]
    text = COMMENT.split(raw or "", maxsplit=1)[0].rstrip()
    if text in ("", "[]", "{}"):
        return {"": None, "[]": [], "{}": {}}[text]
    if text[0] == "[" and text[-1] == "]":
        parts = [part.strip() for part in text[1:-1].split(",")]
        if not all(parts):
            fail(path, number, f"a list written as [a, b] has an empty item: {text!r}")
        return [Node(number, scalar(path, number, part)) for part in parts]
    return text


def token(path, number, line):
    """[number, indent, dash, key, value] of one line, or a stop naming it."""
    found = LINE.fullmatch(line)
    if not found or (found.group(5) is not None and not found.group(2)):
        fail(path, number, f"line has no allowed shape here: {line!r}")
    indent, dash, key, raw, item = found.groups()
    value = scalar(path, number, raw if key else item)
    if key is None and value is None:
        fail(path, number, "a list item has no value")
    return [number, len(indent), bool(dash), key, value]


def parse(path, tokens, start, indent):
    """The block that starts at tokens[start], every line at this indent: a dict of key to Node, or a list of
    Nodes for `- ` items. Returns it with the index after it. Every line is used, or the run stops naming it."""
    as_list = tokens[start][2]
    block, index = ([] if as_list else {}), start
    while index < len(tokens) and tokens[index][1] >= indent:
        number, here, dash, key, value = tokens[index]
        if here != indent:
            fail(path, number, "line is not indented like the other lines of its block")
        if dash != as_list:
            fail(path, number, "a block mixes list items and keys")
        if as_list and key is not None:  # a `- key: value` item: a block of keys that starts after the dash
            tokens[index] = [number, indent + 2, False, key, value]
            item, index = parse(path, tokens, index, indent + 2)
            block.append(Node(number, item))
            continue
        index += 1
        if as_list:
            block.append(Node(number, value))
            continue
        if key in block:
            fail(path, number, f"{key!r} appears twice")
        if value is None:
            if index == len(tokens) or tokens[index][1] <= indent:
                fail(path, number, f"{key!r} has no value")
            value, index = parse(path, tokens, index, tokens[index][1])
        block[key] = Node(number, value)
    return block, index


def read_yaml(path, read, skip=(), label=""):
    """The file's top-level sections as a Node of key to Node. A section in read is parsed in full; a section in
    skip is passed over unread; any other section stops the run."""
    lines = [(n, line) for n, line in enumerate(read_file(path, label), 1)
             if line.strip() and not line.lstrip(" ").startswith("#")]
    if lines and lines[0][1] == "---":
        lines = lines[1:]
    tops = [i for i, (_, line) in enumerate(lines) if not line.startswith(" ")] + [len(lines)]
    if lines and tops[0] != 0:
        fail(path, lines[0][0], "an indented line comes before the first section")
    data = {}
    heads = []
    for here in tops[:-1]:  # every top-level line first, so a stray one stops at its own line
        number, line = lines[here]
        heads.append(token(path, number, line))
        if heads[-1][2] or heads[-1][3] is None:
            fail(path, number, f"a top-level line must be `section:`; indent list items under their key: {line!r}")
    for head, here, after in zip(heads, tops, tops[1:]):
        number = head[0]
        if head[3] in data:
            fail(path, number, f"{head[3]!r} appears twice")
        if head[3] in skip:
            data[head[3]] = None
            continue
        if head[3] not in read:
            fail(path, number, f"{head[3]!r} is not a section; allowed: {', '.join(read + skip)}")
        tokens = [head] + [token(path, n, text) for n, text in lines[here + 1:after]]
        data.update(parse(path, tokens, 0, 0)[0])
    return Node(1, {k: v for k, v in data.items() if v is not None})


def leaf(path, node, shape):
    """One value: text with the named shape, for `until` also a real date."""
    if not isinstance(node.value, str):
        fail(path, node.line, f"expected one {shape} value")
    if not SHAPES[shape].fullmatch(node.value) or (shape == "until" and not rulebook.is_date(node.value)):
        fail(path, node.line, f"{node.value!r} is not an allowed {shape}")
    return node.value


def keys(path, node, required, optional=()):
    """A dict holding every required key and no key outside required and optional."""
    allowed = ", ".join([*required, *optional]) or "none"
    if not isinstance(node.value, dict):
        fail(path, node.line, f"expected keys: {allowed}")
    for key, child in node.value.items():
        if key not in (*required, *optional):
            fail(path, child.line, f"{key!r} is not allowed here; allowed: {allowed}")
    missing = [k for k in required if k not in node.value]
    if missing:
        fail(path, node.line, f"missing {', '.join(missing)}")
    return node.value


def items(path, node, what):
    if not isinstance(node.value, list):
        fail(path, node.line, f"expected a list of {what}")
    return node.value


def read_profile(path):
    """The sections of .harness/profile.yaml that resolve reads, checked against their allowed shapes."""
    data = keys(path, read_yaml(path, READ, SKIP), ["harnesswright"], READ[1:])
    install = keys(path, data["harnesswright"], ["version", "folder"])
    profile = {"version": leaf(path, install["version"], "version"), "folder": leaf(path, install["folder"], "folder"),
               "languages": [], "layers": [], "repository": None, "waivers": [], "limit": DEFAULT_LIMIT,
               "decisions": {}}
    standards = keys(path, data.get("standards", Node(1, {})), [], ["languages", "layers", "repository"])
    for node in items(path, standards.get("languages", Node(1, [])), "language names"):
        profile["languages"].append(leaf(path, node, "language"))
    for node in items(path, standards.get("layers", Node(1, [])), "layers"):
        layer = keys(path, node, ["name", "folder", "version"])
        profile["layers"].append({k: leaf(path, layer[k], k) for k in ("name", "folder", "version")})
    if "repository" in standards:
        profile["repository"] = leaf(path, standards["repository"], "folder")
    seen = {}
    for node in items(path, data.get("waivers", Node(1, [])), "waivers"):
        waiver = {k: leaf(path, v, k) for k, v in keys(path, node, ["rule", "reason", "until", "approved by"]).items()}
        if waiver["rule"] in seen:
            fail(path, node.line, f"{waiver['rule']} already has a waiver on line {seen[waiver['rule']]}")
        seen[waiver["rule"]] = node.line
        profile["waivers"].append({**waiver, "line": node.line})
    if "rules-text-limit" in data:
        node = data["rules-text-limit"]
        profile["limit"] = int(leaf(path, node, "limit"))
        if profile["limit"] > MAX_LIMIT:
            fail(path, node.line, f"rules-text-limit {profile['limit']} is over the maximum of {MAX_LIMIT}")
    decisions = data.get("decisions", Node(1, {}))
    if not isinstance(decisions.value, dict):
        fail(path, decisions.line, "expected one `point: option` line for each decision point")
    for key, node in decisions.value.items():
        profile["decisions"][leaf(path, Node(node.line, key), "key")] = (leaf(path, node, "option"), node.line)
    return profile


def read_layer_yaml(name, folder, version, files):
    """The owner of a layer 3 to 5 folder, after checking its layer.yaml and its version against the profile."""
    path = folder / "layer.yaml"
    files.append(path)
    data = keys(path, read_yaml(path, ("owner", "version"), label=f"layer {name}: "), ["owner", "version"])
    found = leaf(path, data["version"], "version")
    if found != version:
        raise ResolveError(f"layer {name} ({folder}): version {found} is not the profile's {version}")
    return leaf(path, data["owner"], "owner")


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
