"""The standards reader's command: resolve an application's rule layers (plan/b01-plan.md part e).

Standard library only. Shipped in each release skill's scripts/ beside rulebook.py, reach.py and copyform.py, and
imports only them. One rule governs it, as it does rulebook.py: every line and value it reads has a shape listed
here, and anything else stops the run naming the file and line (HW-AG-09). Part e1a reads and checks the inputs of
docs/design/03-standards.md "Resolving the rules for an application" and docs/design/07-repo-profile.md; parts e1b
and e2 combine them and write rules.md and the rules texts.

Run: python3 resolve.py --repo REPO --run RUN-ID --date YYYY-MM-DD
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import rulebook
from rulebook import DP_ID, EVERY_ROLE, RULE_ID, RulebookError, fail

PROFILE = ".harness/profile.yaml"
MAX_LIMIT = 60000
DEFAULT_LIMIT = 30000
READ = ("harnesswright", "standards", "waivers", "rules-text-limit", "decisions")
SKIP = ("toolchain", "scripts", "models", "capabilities", "process")  # doc 07's sections that resolve does not read
VALUE = re.compile(f"{rulebook.PRINTABLE}+")
ACCOUNT = r"[A-Za-z0-9._-]+"
LEVELS = ("COMP", "DEPT", "TEAM")  # company, department, team: layers 3 to 5, most general first
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
OPTION_NAME = re.compile(r"- `([a-z0-9-]+)`: .*")
# A change relation is allowed only between these kinds (plan/b01-plan.md "Change relations").
RELATIONS = {"Tightens": ({"floor"}, {"floor"}), "Binds": ({"choice"}, {"decision point"}),
             "Overrides": ({"principle", "idiom", "choice"}, {"principle", "idiom", "choice"})}


class ResolveError(RulebookError):
    """An input that stops the run, named with its file and line or its layer."""


@dataclass
class Node:
    """One parsed value and the line it starts on: text, a list of Nodes, or a dict of key to Node."""
    line: int
    value: object


@dataclass
class Source:
    """One layer the run reads, most general first."""
    prefix: str  # the ID prefix its rules carry: CORE, JAVA-SPRING, COMP-ACME, APP
    folder: Path
    owner: str
    rules: dict = field(default_factory=dict)  # ID -> rulebook.Rule


@dataclass
class Inputs:
    version: str
    release: Path
    sources: list  # Source, most general first
    roles: set
    decisions: dict  # decision point ID -> (option, profile line)
    waivers: list  # dicts with rule, reason, until, approved by, line; not expired
    expired: list  # the same, `until` before the run date
    limit: int
    files: list = field(default_factory=list)  # every file read, in reading order



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


def prefix_of(rule_id):
    """The layer prefix of an ID: CORE for CORE-TEST-03 and CORE-DP-STACK, JAVA-SPRING for JAVA-SPRING-WEB-01."""
    return rule_id.split("-DP-")[0] if DP_ID.fullmatch(rule_id) else "-".join(rule_id.split("-")[:-2])


def options(rule):
    return [OPTION_NAME.fullmatch(line).group(1) for line in rule.parts["Options"][1:] if OPTION_NAME.fullmatch(line)]


def read_source(name, prefixes, folder, owner, files):
    """One layer folder. Every rule in it carries one prefix, which must be one of prefixes."""
    if not folder.is_dir():
        raise ResolveError(f"layer {name}: folder {folder} is missing or cannot be read")
    rules = rulebook.read_layer(folder).rules
    files += sorted(p for p in folder.glob("*.md") if p.name not in rulebook.NOT_RULE_FILES)
    found = {prefix_of(rule_id) for rule_id in rules}
    if len(found) != 1 or not found <= set(prefixes):
        raise ResolveError(f"layer {name} ({folder}): its rule IDs carry {sorted(found) or 'no rule'}; "
                           f"they must all carry one of {', '.join(prefixes)}")
    return Source(found.pop(), folder, owner, rules)


def read_layer_yaml(name, folder, version, files):
    """The owner of a layer 3 to 5 folder, after checking its layer.yaml and its version against the profile."""
    path = folder / "layer.yaml"
    files.append(path)
    data = keys(path, read_yaml(path, ("owner", "version"), label=f"layer {name}: "), ["owner", "version"])
    found = leaf(path, data["version"], "version")
    if found != version:
        raise ResolveError(f"layer {name} ({folder}): version {found} is not the profile's {version}")
    return leaf(path, data["owner"], "owner")


def load(repo, today):
    """Read and check every input of a run; any break of the plan's stops raises ResolveError."""
    repo = Path(repo)
    path = repo / PROFILE
    profile, files = read_profile(path), [path]
    release = repo / profile["folder"]
    manifest_path = release / "manifest.json"
    try:
        found = json.loads(manifest_path.read_text(encoding="utf-8")).get("rulebook-version")
    except (OSError, UnicodeDecodeError, ValueError, AttributeError):
        raise ResolveError(f"release: {manifest_path} is missing or cannot be read") from None
    files += [manifest_path, release / "roles.md"]
    if found != profile["version"]:
        raise ResolveError(f"release ({release}): version {found} is not the profile's {profile['version']}")
    roles = set(rulebook.read_roles(release / "roles.md")["roles"])
    sources = [read_source("CORE", ("CORE",), release / "rules" / "core", "harnesswright", files)]
    for language in profile["languages"]:
        folder = release / "rules" / language
        if not folder.is_dir():
            raise ResolveError(f"language {language} is not in the release ({folder})")
        sources.append(read_source(language, (language.upper(),), folder, "harnesswright", files))
    for layer in profile["layers"]:
        folder = repo / layer["folder"]
        owner = read_layer_yaml(layer["name"], folder, layer["version"], files)
        prefixes = tuple(f"{level}-{layer['name'].upper()}" for level in LEVELS)
        sources.append(read_source(layer["name"], prefixes, folder, owner, files))
    levels = [LEVELS.index(s.prefix.split("-")[0]) for s in sources if s.prefix.split("-")[0] in LEVELS]
    if levels != sorted(set(levels)):
        raise ResolveError("standards.layers must list at most one company, then department, then team layer, "
                           "in that order")
    if profile["repository"]:
        sources.append(read_source("application", ("APP",), repo / profile["repository"], "the application owner",
                                   files))
    check_rules(sources, roles)
    inputs = Inputs(profile["version"], release, sources, roles, check_decisions(path, profile, sources), [], [],
                    profile["limit"], files)
    check_waivers(path, profile, sources, today, inputs)
    return inputs


def active(source):
    return [r for r in source.rules.values() if r.status == "active"]


def check_rules(sources, roles):
    """Applies to names known roles; each change relation is allowed and reaches a more general layer. No ID can be
    in two layers: each layer has its own prefix (read_source), and no level is listed twice (load)."""
    for index, source in enumerate(sources):
        for rule in active(source):
            where = f"{rule.file}:{rule.line}: {rule.id}"
            unknown = [n for n in rule.applies_to if n != EVERY_ROLE and n not in roles]
            if index and unknown:
                raise ResolveError(f"{where}: Applies to names roles not in the release's roles.md: {unknown}")
            relation = next((name for name in rulebook.CHANGES if name in rule.parts), None)
            if relation is None:
                continue
            target = next((s.rules[rule.changes] for s in sources[:index] if rule.changes in s.rules), None)
            if target is None or target.status != "active":
                raise ResolveError(f"{where}: {relation} {rule.changes}, which no more general layer holds active")
            kinds, target_kinds = RELATIONS[relation]
            if rule.kind not in kinds or target.kind not in target_kinds:
                raise ResolveError(f"{where}: {relation} may not go from a {rule.kind} to a {target.kind}; it goes "
                                   f"from {'/'.join(sorted(kinds))} to {'/'.join(sorted(target_kinds))}")
            if relation == "Binds" and rule.option not in options(target):
                raise ResolveError(f"{where}: option {rule.option!r} is not one of {target.id}'s Options")


def check_decisions(path, profile, sources):
    """Each profile decision names exactly one active decision point and one of its Options."""
    points = [r for s in sources for r in active(s) if r.is_decision_point]
    bound = {}
    for key, (option, number) in profile["decisions"].items():
        named = [r for r in points if r.id.endswith("-DP-" + key.upper())]
        if len(named) != 1:
            fail(path, number, f"decisions key {key!r} names {len(named)} active decision points; it must name one")
        if option not in options(named[0]):
            fail(path, number, f"option {option!r} is not one of {named[0].id}'s Options")
        bound[named[0].id] = (option, number)
    return bound


def check_waivers(path, profile, sources, today, inputs):
    """Each waiver names an active rule that is not a floor; one whose `until` has passed is set aside."""
    rules = {r.id: r for s in sources for r in active(s)}
    for waiver in profile["waivers"]:
        rule = rules.get(waiver["rule"])
        if rule is None:
            fail(path, waiver["line"], f"waiver of {waiver['rule']}, which no layer holds active")
        if rule.kind == "floor":
            fail(path, waiver["line"], f"waiver of {rule.id}, a floor; a floor is never waived (HW-RULE-06)")
        expired = date.fromisoformat(waiver["until"]) < today
        (inputs.expired if expired else inputs.waivers).append(waiver)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    args = parser.parse_args(argv)
    try:
        load(args.repo, args.date)
    except RulebookError as error:
        print(f"resolve stopped: {error}", file=sys.stderr)
        return 1
    print("resolve: inputs checked; writing rules.md is not built yet (B0.1 part e1b)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
