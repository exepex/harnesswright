"""The standards reader's command: resolve an application's rule layers (plan/b01-plan.md part e).

Standard library only. Shipped in each release skill's scripts/ beside rulebook.py, reach.py, copyform.py and
repoprofile.py, and imports only them. It reads the team settings with repoprofile.py, then every layer the run
uses, and stops on any break of docs/design/03-standards.md "Resolving the rules for an application" and
docs/design/07-repo-profile.md, naming the file and line or the layer and folder (HW-AG-09). Part e1a reads and
checks these inputs; parts e1b and e2 combine them and write rules.md and the rules texts.

Run: python3 resolve.py --repo REPO --run RUN-ID --date YYYY-MM-DD
"""

import argparse
import hashlib
import os
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
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
RULES_MD = ".harness/runs/{run}/rules.md"
# A change relation is allowed only between these kinds (plan/b01-plan.md "Change relations").
WAIVABLE = ("principle", "idiom", "choice")
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
    for index, (language, number) in enumerate(zip(profile["languages"], profile["language lines"])):
        base = language.split("-")[0]  # a framework `x-y` belongs to the language `x`
        if base != language and base not in profile["languages"][:index]:
            fail(path, number, f"standards.languages lists framework {language} without its language {base} before it")
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
            if relation == "Overrides" and "Binds" in target.parts:
                raise ResolveError(f"{where}: Overrides {target.id}, a binding; a binding changes only by binding "
                                   "its point again")
            if relation == "Binds" and rule.option not in target.options:
                raise ResolveError(f"{where}: option {rule.option!r} is not one of {target.id}'s Options")


def check_decisions(path, profile, sources):
    """Each profile decision names exactly one active decision point and one of its Options."""
    points = [r for s in sources for r in active(s) if r.is_decision_point]
    bound = {}
    for key, (option, number) in profile["decisions"].items():
        named = [r for r in points if r.id.endswith("-DP-" + key.upper())]
        if len(named) != 1:
            fail(path, number, f"decisions key {key!r} names {len(named)} active decision points; it must name one")
        if option not in named[0].options:
            fail(path, number, f"option {option!r} is not one of {named[0].id}'s Options")
        bound[named[0].id] = (option, number)
    return bound


def check_waivers(path, profile, sources, today, inputs):
    """Each waiver names an active principle, idiom or choice that binds no decision point; one whose `until` has
    passed is set aside. A floor is never waived (HW-RULE-06); a binding changes only by binding the point again."""
    rules = {r.id: r for s in sources for r in active(s)}
    for waiver in profile["waivers"]:
        rule = rules.get(waiver["rule"])
        if rule is None:
            fail(path, waiver["line"], f"waiver of {waiver['rule']}, which no layer holds active")
        if rule.kind not in WAIVABLE or "Binds" in rule.parts:
            fail(path, waiver["line"], f"waiver of {rule.id}, a {'binding' if 'Binds' in rule.parts else rule.kind}"
                                       "; only a principle, idiom or choice that binds no decision point is waived "
                                       "(a floor never is, HW-RULE-06; bind a point again in decisions)")
        expired = date.fromisoformat(waiver["until"]) < today
        (inputs.expired if expired else inputs.waivers).append(waiver)


@dataclass
class Resolved:
    """Doc 03 steps 1 to 4: the rules that apply, in layer order, and what each decision point resolves to."""
    rules: dict = field(default_factory=dict)  # ID -> (rule, layer prefix, change text), most general first
    replaced: dict = field(default_factory=dict)  # ID of a rule that no longer applies -> the ID that replaced it
    points: dict = field(default_factory=dict)  # decision point ID -> (option, where it comes from)
    waivers: dict = field(default_factory=dict)  # waived rule ID -> its waiver


def combine(inputs):
    """Apply each layer most general first, then the profile's bindings, then the defaults, then the waivers.
    One rule: a rule that loses to a more specific input (an override, or a later binding of its point) leaves the
    rules and is recorded in `replaced`, and a change relation must name a rule that still applies."""
    done, bound, app_binds = Resolved(), {}, {}  # bound: decision point ID -> the binding rule that applies now

    def replace(old, new):
        del done.rules[old]
        done.replaced[old] = new

    for source in inputs.sources:
        binds = {}  # decision point ID -> the rule in this layer that binds it
        for rule in active(source):
            relation = next((name for name in rulebook.CHANGES if name in rule.parts), None)
            change = f"{relation} {rule.changes}" if relation else ""
            change += f": {rule.option}" if relation == "Binds" else ""
            if relation and rule.changes in done.replaced:
                by = done.replaced[rule.changes]
                advice = ("its layer's owner keeps one of the two" if prefix_of(by) == source.prefix else
                          "name that rule instead")
                raise ResolveError(f"{rule.file}:{rule.line}: {rule.id} {relation} {rule.changes}, which {by} "
                                   f"already replaces; {advice}")
            if relation == "Overrides":
                replace(rule.changes, rule.id)
            if relation == "Binds":
                if rule.changes in binds:
                    raise ResolveError(f"{rule.file}:{rule.line}: {rule.id} binds {rule.changes}, which "
                                       f"{binds[rule.changes].id} already binds in layer {source.prefix}")
                if rule.changes in bound:
                    replace(bound[rule.changes].id, rule.id)
                binds[rule.changes] = bound[rule.changes] = rule
            done.rules[rule.id] = (rule, source.prefix, change)
        app_binds = binds if source.prefix == "APP" else app_binds
    for point, (option, number) in inputs.decisions.items():
        if point in app_binds:
            fail(inputs.files[0], number, f"{point} is bound twice in the application layer: here and by "
                                          f"{app_binds[point].id}")
        if point in bound:
            replace(bound[point].id, "profile decisions")
    done.points = {point: (rule.option, rule.id) for point, rule in bound.items()}
    done.points.update({point: (option, "profile decisions") for point, (option, _) in inputs.decisions.items()})
    for rule, _, _ in done.rules.values():
        if rule.is_decision_point and rule.id not in done.points:
            done.points[rule.id] = (rule.default, "default")
    done.waivers = {w["rule"]: w for w in inputs.waivers}
    return done


def last(done, rule_id):
    """The rule that replaces rule_id in the end, following a chain of replacements."""
    while rule_id in done.replaced:
        rule_id = done.replaced[rule_id]
    return rule_id


def cell(text):
    return str(text).replace("|", "\\|")


def rules_md(repo, run, today, inputs, done):
    """The resolved standards file: no rule text, only IDs, layers, kinds, changes, waivers and file hashes."""
    def row(*cells):
        return "| " + " | ".join(cell(c) for c in cells) + " |"
    lines = ["# Resolved standards", "", f"- **Run:** {run}", f"- **Date:** {today.isoformat()}",
             f"- **Release:** {inputs.version}", "", "## Rules", "", "| ID | Layer | Kind | Changes | Waiver |",
             "|---|---|---|---|---|"]
    for rule_id, (rule, layer, change) in done.rules.items():
        waiver = done.waivers.get(rule_id)
        lines.append(row(rule_id, layer, rule.kind, change, f"waived until {waiver['until']}" if waiver else ""))
    lines += ["", "## Decision points", "", "| Point | Option | From |", "|---|---|---|"]
    lines += [row(point, option, source) for point, (option, source) in done.points.items()]
    lines += ["", "## Waivers", "", "| Rule | Reason | Until | Approved by | Status |", "|---|---|---|---|---|"]
    for waiver in inputs.waivers + inputs.expired:
        status = ("expired" if waiver in inputs.expired else
                  f"replaced by {last(done, waiver['rule'])}" if waiver["rule"] in done.replaced else "applied")
        lines.append(row(waiver["rule"], waiver["reason"], waiver["until"], waiver["approved by"], status))
    lines += ["", "## Replaced", "", "| Rule | Replaced by |", "|---|---|"]
    lines += [row(rule_id, by) for rule_id, by in done.replaced.items()]
    lines += ["", "## Files read", "", "| SHA-256 | File |", "|---|---|"]
    for path in inputs.files:
        name = Path(os.path.relpath(Path(path).resolve(), Path(repo).resolve())).as_posix()
        lines.append(row(hashlib.sha256(Path(path).read_bytes()).hexdigest(), name))
    return "\n".join(lines) + "\n"


def write_rules_md(repo, run, text):
    """Write rules.md once per run. If the run already has one, the new text must be the same bytes."""
    path = Path(repo) / RULES_MD.format(run=run)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as file:  # created here or not at all, so a second resolve never overwrites it
            file.write(text.encode("utf-8"))
    except FileExistsError:
        if path.read_bytes() != text.encode("utf-8"):
            raise ResolveError(f"{path} already exists and differs from this resolve: an input changed during "
                               "the run; start a new run") from None
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    args = parser.parse_args(argv)
    try:
        if not RUN_ID.fullmatch(args.run):
            raise ResolveError(f"run id {args.run!r} must be letters, digits, '.', '_' or '-'")
        inputs = load(args.repo, args.date)
        path = write_rules_md(args.repo, args.run, rules_md(args.repo, args.run, args.date, inputs, combine(inputs)))
    except RulebookError as error:
        print(f"resolve stopped: {error}", file=sys.stderr)
        return 1
    print(f"resolve: wrote {path}; the rules texts are not built yet (B0.1 part e2)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
