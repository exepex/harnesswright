"""The standards reader's command: resolve an application's rule layers (plan/b01-plan.md part e).

Standard library only. Shipped in each release skill's scripts/ beside rulebook.py, reach.py, copyform.py and
repoprofile.py, and imports only them. It reads the team settings with repoprofile.py, then every layer the run
uses, and stops on any break of docs/design/03-standards.md "Resolving the rules for an application" and
docs/design/07-repo-profile.md, naming the file and line or the layer and folder (HW-AG-09). Part e1a reads and
checks these inputs; parts e1b and e2 combine them and write rules.md and the rules texts.

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
from repoprofile import PROFILE, RulebookError, ResolveError, read_layer_yaml, read_profile
from rulebook import DP_ID, EVERY_ROLE, fail

LEVELS = ("COMP", "DEPT", "TEAM")  # company, department, team: layers 3 to 5, most general first
OPTION_NAME = re.compile(r"- `([a-z0-9-]+)`: .*")
# A change relation is allowed only between these kinds (plan/b01-plan.md "Change relations").
RELATIONS = {"Tightens": ({"floor"}, {"floor"}), "Binds": ({"choice"}, {"decision point"}),
             "Overrides": ({"principle", "idiom", "choice"}, {"principle", "idiom", "choice"})}


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



def prefix_of(rule_id):
    """The layer prefix of an ID: CORE for CORE-TEST-03 and CORE-DP-STACK, JAVA-SPRING for JAVA-SPRING-WEB-01."""
    return rule_id.split("-DP-")[0] if DP_ID.fullmatch(rule_id) else "-".join(rule_id.split("-")[:-2])


def options(rule):
    return [OPTION_NAME.fullmatch(line).group(1) for line in rule.parts["Options"][1:] if OPTION_NAME.fullmatch(line)]


def add_source(sources, name, prefixes, folder, owner, files):
    """Read one layer folder and add it to sources. Every layer passes through here: its folder and files must be
    readable, it holds at least one rule, every rule carries one of prefixes, and no other layer has its prefix."""
    paths = sorted(p for p in folder.glob("*.md") if p.name not in rulebook.NOT_RULE_FILES) if folder.is_dir() else []
    for path in paths:
        try:
            path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ResolveError(f"layer {name} ({folder}): {path} cannot be read ({type(error).__name__})") from None
    if not paths:
        raise ResolveError(f"layer {name}: folder {folder} is missing, cannot be read or holds no rule file")
    rules = rulebook.read_layer(folder).rules
    files += paths
    found = {prefix_of(rule_id) for rule_id in rules}
    if len(found) != 1 or not found <= set(prefixes):
        raise ResolveError(f"layer {name} ({folder}): its rule IDs carry {sorted(found) or 'no rule'}; "
                           f"they must all carry one of {', '.join(prefixes)}")
    prefix = found.pop()
    other = next((s for s in sources if s.prefix == prefix), None)
    if other:
        raise ResolveError(f"layer {name} ({folder}) carries {prefix}, which {other.folder} already holds; "
                           "each layer is listed once")
    sources.append(Source(prefix, folder, owner, rules))
    return sources[-1]


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
    try:
        roles = set(rulebook.read_roles(release / "roles.md")["roles"])
    except (OSError, UnicodeDecodeError):
        raise ResolveError(f"release: {release / 'roles.md'} is missing or cannot be read") from None
    sources = []
    add_source(sources, "CORE", ("CORE",), release / "rules" / "core", "harnesswright", files)
    for language in profile["languages"]:
        base = language.split("-")[0]
        if base != language and base not in profile["languages"][:profile["languages"].index(language)]:
            raise ResolveError(f"{path}: standards.languages lists framework {language} without its language "
                               f"{base} before it")
        add_source(sources, language, (language.upper(),), release / "rules" / language, "harnesswright", files)
    level = -1
    for layer in profile["layers"]:
        folder = repo / layer["folder"]
        owner = read_layer_yaml(layer["name"], folder, layer["version"], files)
        prefixes = tuple(f"{lvl}-{layer['name'].upper()}" for lvl in LEVELS)
        here = LEVELS.index(add_source(sources, layer["name"], prefixes, folder, owner, files).prefix.split("-")[0])
        if here <= level:
            fail(path, layer["line"], f"layer {layer['name']} ({folder}) is a {LEVELS[here]} layer listed after a "
                 f"{LEVELS[level]} layer; list at most one company, then department, then team layer")
        level = here
    if profile["repository"]:
        add_source(sources, "application", ("APP",), repo / profile["repository"], "the application owner", files)
    check_rules(sources, roles)
    inputs = Inputs(profile["version"], release, sources, roles, check_decisions(path, profile, sources), [], [],
                    profile["limit"], files)
    check_waivers(path, profile, sources, today, inputs)
    return inputs


def active(source):
    return [r for r in source.rules.values() if r.status == "active"]


def check_rules(sources, roles):
    """Applies to names known roles; each change relation is allowed and reaches a more general layer. No ID can be
    in two layers: each layer has its own prefix (add_source)."""
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
