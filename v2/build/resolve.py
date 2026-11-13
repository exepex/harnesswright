"""The standards reader's command: resolve an application's rule layers (plan/b01-plan.md part e).

Standard library only. Shipped in each release skill's scripts/ beside rulebook.py, reach.py, copyform.py,
repoprofile.py and runfiles.py, and imports only them. It reads the team settings with repoprofile.py, then every
layer the run uses, and stops on any break of docs/design/03-standards.md "Resolving the rules for an application"
and docs/design/07-repo-profile.md, naming the file and line or the layer and folder (HW-AG-09). Part e1a reads and
checks these inputs; parts e1b and e2 combine them, and runfiles.py writes rules.md and the rules texts.

Run: python3 resolve.py --repo REPO --run RUN-ID --date YYYY-MM-DD
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import reach
import rulebook
import runfiles
from repoprofile import PROFILE, RulebookError, ResolveError, read_layer_yaml, read_profile
from rulebook import DP_ID, EVERY_ROLE, fail

LEVELS = ("COMP", "DEPT", "TEAM")  # company, department, team: layers 3 to 5, most general first
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
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
    manifest: dict = field(default_factory=dict)  # the release manifest: its version and each skill's entry
    jobs: dict = field(default_factory=dict)  # the release roles file's Jobs table



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


ENTRY = {"job": str, "rest": bool, "roles": list, "areas": list, "copied-ids": list}  # what resolve reads of a skill


def read_manifest(path):
    """The release manifest: its version, and per skill the entry keys resolve reads, each of its shape."""
    try:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
        ok = isinstance(manifest["rulebook-version"], str) and isinstance(manifest["skills"], dict) and all(
            isinstance(e, dict) and all(isinstance(e.get(k), t) for k, t in ENTRY.items())
            for e in manifest["skills"].values())
    except (OSError, UnicodeDecodeError, ValueError, TypeError, KeyError):
        ok = False
    if not ok:
        raise ResolveError(f"release: {path} is missing or cannot be read as a release manifest")
    return manifest


def load(repo, today):
    """Read and check every input of a run; any break of the plan's stops raises ResolveError."""
    repo = Path(repo)
    path = repo / PROFILE
    profile, files = read_profile(path), [path]
    release = repo / profile["folder"]
    manifest_path = release / "manifest.json"
    manifest = read_manifest(manifest_path)
    files += [manifest_path, release / "roles.md"]
    if manifest["rulebook-version"] != profile["version"]:
        raise ResolveError(f"release ({release}): version {manifest['rulebook-version']} is not the profile's "
                           f"{profile['version']}")
    try:
        table = rulebook.read_roles(release / "roles.md")
    except (OSError, UnicodeDecodeError):
        raise ResolveError(f"release: {release / 'roles.md'} is missing or cannot be read") from None
    roles = set(table["roles"])
    for job in sorted(set(table["jobs"]) | {e["job"] for e in manifest["skills"].values()}):
        listed = table["jobs"].get(job, {}).get("Skills in order", [])
        named = sorted(n for n, e in manifest["skills"].items() if e["job"] == job)
        if sorted(listed) != named:  # one list of a job's skills, so each skill's job and `rest` areas are known
            raise ResolveError(f"release: job {job} lists skills {listed} in roles.md, but {manifest_path} gives "
                               f"it {named}")
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
                    profile["limit"], files, manifest, table["jobs"])
    check_waivers(path, profile, sources, today, inputs)
    return inputs


def language_of(source):
    """The language a language or framework layer belongs to (JAVA for JAVA-SPRING), or None for any other layer.
    It takes a Source or a layer prefix."""
    prefix = getattr(source, "prefix", source)
    base = prefix.split("-")[0]
    return None if prefix == "APP" or base in ("CORE",) + LEVELS else base


def builds_on(source, prefix):
    """A language or framework layer builds on CORE and its own language only; any other layer builds on every more
    general layer. No two languages are ranked, so neither may change the other's rules."""
    return language_of(source) is None or prefix == "CORE" or language_of(prefix) == language_of(source)


def stacks(sources):
    """One stack per language, resolved on its own: CORE, the language and its frameworks, then layers 3 to 6. An
    application with no language has one stack, named core."""
    languages = list(dict.fromkeys(language_of(s) for s in sources if language_of(s)))
    return [(name.lower(), [s for s in sources if language_of(s) in (None, name)]) for name in languages or ["CORE"]]


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
            if not builds_on(source, prefix_of(target.id)):
                raise ResolveError(f"{where}: {relation} {target.id}, a rule of another language; a language "
                                   "changes only CORE rules and its own language's")
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
    """Each profile decision names one active decision point in each stack that holds one, at least one in all, and
    one of each named point's Options. So `boilerplate` binds JAVA-DP-BOILERPLATE and KOTLIN-DP-BOILERPLATE alike."""
    bound = {}
    for key, (option, number) in profile["decisions"].items():
        named = {}
        for _, stack in stacks(sources):
            here = [r for s in stack for r in active(s) if r.is_decision_point and r.id.endswith("-DP-" + key.upper())]
            if len(here) > 1:
                fail(path, number, f"decisions key {key!r} names {len(here)} active decision points in one stack "
                                   f"({', '.join(r.id for r in here)}); it must name one")
            named.update({r.id: r for r in here})
        if not named:
            fail(path, number, f"decisions key {key!r} names 0 active decision points; it must name one")
        for point in named.values():
            if option not in point.options:
                fail(path, number, f"option {option!r} is not one of {point.id}'s Options")
            bound[point.id] = (option, number)
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
    """Doc 03 steps 1 to 4 for one stack: the rules that apply, in layer order, and what each point resolves to."""
    stack: str
    rules: dict = field(default_factory=dict)  # ID -> (rule, layer prefix, change text), most general first
    replaced: dict = field(default_factory=dict)  # ID of a rule that no longer applies -> the ID that replaced it
    points: dict = field(default_factory=dict)  # decision point ID -> (option, where it comes from)
    waivers: list = field(default_factory=list)  # the waivers and expired waivers of rules in this stack

    def last(self, rule_id):
        """The rule that replaces rule_id in the end, following a chain of replacements."""
        while rule_id in self.replaced:
            rule_id = self.replaced[rule_id]
        return rule_id


def combine(inputs):
    """Resolve each stack (one per language) on its own."""
    return [combine_stack(inputs, name, sources) for name, sources in stacks(inputs.sources)]


def combine_stack(inputs, name, sources):
    """Apply each layer most general first, then the profile's bindings, then the defaults, then the waivers.
    One rule: a rule that loses to a more specific input (an override, or a later binding of its point) leaves the
    rules and is recorded in `replaced`, and a change relation must name a rule that still applies. A rule that
    changes a rule of another stack's language belongs to that stack only."""
    done, bound, app_binds = Resolved(name), {}, {}  # bound: decision point ID -> the binding rule that applies now

    def replace(old, new):
        del done.rules[old]
        done.replaced[old] = new

    for source in sources:
        binds = {}  # decision point ID -> the rule in this layer that binds it
        for rule in active(source):
            relation = next((name for name in rulebook.CHANGES if name in rule.parts), None)
            change = f"{relation} {rule.changes}" if relation else ""
            change += f": {rule.option}" if relation == "Binds" else ""
            if relation and rule.changes not in done.rules and rule.changes not in done.replaced:
                continue  # it changes another language's rule, so it belongs to that language's stack only
            target = rule.changes
            if relation and prefix_of(target) == "CORE" and not language_of(source) and source.prefix != "CORE":
                while target in done.replaced and language_of(prefix_of(done.replaced[target])):
                    target = done.replaced[target]  # a language's replacement stands in the principles rule's place
            if relation and target in done.replaced:
                by = done.replaced[target]
                advice = ("its layer's owner keeps one of the two" if prefix_of(by) == source.prefix else
                          "name that rule instead")
                raise ResolveError(f"{rule.file}:{rule.line}: {rule.id} {relation} {target}, which {by} "
                                   f"already replaces; {advice}")
            if relation == "Overrides":
                replace(target, rule.id)
            if relation == "Binds":
                if rule.changes in binds:
                    raise ResolveError(f"{rule.file}:{rule.line}: {rule.id} binds {rule.changes}, which "
                                       f"{binds[rule.changes].id} already binds in layer {source.prefix}")
                if rule.changes in bound:
                    replace(bound[rule.changes].id, rule.id)
                binds[rule.changes] = bound[rule.changes] = rule
            done.rules[rule.id] = (rule, source.prefix, change)
        app_binds = binds if source.prefix == "APP" else app_binds
    decisions = {point: value for point, value in inputs.decisions.items() if point in done.rules}
    for point, (option, number) in decisions.items():
        if point in app_binds:
            fail(inputs.files[0], number, f"{point} is bound twice in the application layer: here and by "
                                          f"{app_binds[point].id}")
        if point in bound:
            replace(bound[point].id, "profile decisions")
    done.points = {point: (rule.option, rule.id) for point, rule in bound.items()}
    done.points.update({point: (option, "profile decisions") for point, (option, _) in decisions.items()})
    for rule, _, _ in done.rules.values():
        if rule.is_decision_point and rule.id not in done.points:
            done.points[rule.id] = (rule.default, "default")
    done.waivers = [w for w in inputs.waivers + inputs.expired if w["rule"] in done.rules or w["rule"] in done.replaced]
    return done


def run_files(repo, run, today, inputs):
    """What the run writes: rules.md, one rules text per skill and stack (path -> text), and the rules texts parked
    over the ceiling ((skill, stack) -> size, owner of its largest layer, sizes per layer and area)."""
    stacks_done = combine(inputs)
    held = [[r for s in sources for r in active(s) if r.id in done.rules or r.id in done.replaced]  # a rule that
            for (_, sources), done in zip(stacks(inputs.sources), stacks_done)]  # changes another stack's is not here
    texts, parked = {}, {}
    for name in sorted(inputs.manifest["skills"]):
        for rules, done in zip(held, stacks_done):
            text, full = runfiles.rules_text(name, inputs, rules, done)
            if reach.size(text) > inputs.limit:
                parked[(name, done.stack)] = (reach.size(text), *runfiles.largest_owner(full, inputs))
            else:
                texts[Path(repo) / runfiles.RULES_TEXT.format(run=run, skill=name, stack=done.stack)] = text
    summary = {key: (size, owner) for key, (size, owner, _) in parked.items()}
    return runfiles.rules_md(repo, run, today, inputs, stacks_done, texts, summary), texts, parked


def main(argv=None):
    """Exit 0 when every rules text is written, 3 when one is parked over the ceiling, 1 when the run stops."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    args = parser.parse_args(argv)
    try:
        if not RUN_ID.fullmatch(args.run):
            raise ResolveError(f"run id {args.run!r} must be letters, digits, '.', '_' or '-'")
        inputs = load(args.repo, args.date)
        text, texts, parked = run_files(args.repo, args.run, args.date, inputs)
        path = runfiles.write_once(Path(args.repo) / runfiles.RULES_MD.format(run=args.run), text)
        for rules_text_path, rules_text in texts.items():
            runfiles.write_once(rules_text_path, rules_text)
    except RulebookError as error:
        print(f"resolve stopped: {error}", file=sys.stderr)
        return 1
    print(f"resolve: wrote {path} and {len(texts)} rules texts", file=sys.stderr)
    for (name, stack), (size, owner, sizes) in parked.items():
        print(f"resolve: parked {name} ({stack}): its rules text is {size} characters, over the limit of "
              f"{inputs.limit}; it goes to {owner}. Sizes per layer and area:", file=sys.stderr)
        for (layer, area), count in sorted(sizes.items()):
            print(f"  {layer} {area}: {count}", file=sys.stderr)
    return 3 if parked else 0


if __name__ == "__main__":
    sys.exit(main())
