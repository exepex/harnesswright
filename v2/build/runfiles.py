"""The files one run writes beside its rules: `rules.md` and one `rules-text-<skill>.md` per release skill (doc 03).

Standard library only. `rules.md` holds no rule text: per stack (one per language) it lists the rules that apply,
the decision points, the waivers and the replaced rules, then the SHA-256 of every file read and every rules text
written, and the skills parked over the ceiling.

A rules text holds, per stack, the rules from layers 2 to 6 that reach the skill's run and the CORE rules that reach
it but the skill did not copy, in full; one line for each change to a rule that reaches (what replaced it, what
tightened it, its waiver); one line per decision point that reaches, with its option and where that came from; and a
read-back block. What reaches is reach.reach over every active rule of the stack, with the skill's copied IDs as
cited, so a rule that changes a copied CORE rule reaches too (reviews/release-design/size-final.md section 1). A rule
that lost to a more specific input appears only as its "replaced by" line, never in full.
"""

import hashlib
import os
from pathlib import Path

import copyform
import reach
from repoprofile import ResolveError

RUN = ".harness/runs/{run}"
RULES_MD = RUN + "/rules.md"
RULES_TEXT = RUN + "/rules-text-{skill}.md"
MARKS = "### Changes to rules that reach this run"
POINTS = "### Decision points"


def cell(text):
    return str(text).replace("|", "\\|")


def row(*cells):
    return "| " + " | ".join(cell(c) for c in cells) + " |"


def relative(repo, path):
    return Path(os.path.relpath(Path(path).resolve(), Path(repo).resolve())).as_posix()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def stack_md(inputs, done):
    """One stack's sections of rules.md."""
    applied = {w["rule"]: w for w in done.waivers if w not in inputs.expired}
    lines = ["", f"## Stack: {done.stack}", "", "### Rules", "", "| ID | Layer | Kind | Changes | Waiver |",
             "|---|---|---|---|---|"]
    for rule_id, (rule, layer, change) in done.rules.items():
        waiver = applied.get(rule_id)
        lines.append(row(rule_id, layer, rule.kind, change, f"waived until {waiver['until']}" if waiver else ""))
    lines += ["", "### Decision points", "", "| Point | Option | From |", "|---|---|---|"]
    lines += [row(point, option, source) for point, (option, source) in done.points.items()]
    lines += ["", "### Waivers", "", "| Rule | Reason | Until | Approved by | Status |", "|---|---|---|---|---|"]
    for waiver in done.waivers:
        status = ("expired" if waiver in inputs.expired else
                  f"replaced by {done.last(waiver['rule'])}" if waiver["rule"] in done.replaced else "applied")
        lines.append(row(waiver["rule"], waiver["reason"], waiver["until"], waiver["approved by"], status))
    lines += ["", "### Replaced", "", "| Rule | Replaced by |", "|---|---|"]
    return lines + [row(rule_id, by) for rule_id, by in done.replaced.items()]


def rules_md(repo, run, today, inputs, stacks_done, texts=None, parked=None):
    """The resolved standards file. texts maps each written rules text's path to its text; parked maps each parked
    skill to (size, owner of its largest layer)."""
    lines = ["# Resolved standards", "", f"- **Run:** {run}", f"- **Date:** {today.isoformat()}",
             f"- **Release:** {inputs.version}"]
    for done in stacks_done:
        lines += stack_md(inputs, done)
    lines += ["", "## Files read", "", "| SHA-256 | File |", "|---|---|"]
    lines += [row(sha(Path(path).read_bytes()), relative(repo, path)) for path in inputs.files]
    lines += ["", "## Rules texts", "", "| SHA-256 | File |", "|---|---|"]
    lines += [row(sha(text.encode("utf-8")), relative(repo, path)) for path, text in (texts or {}).items()]
    lines += ["", "## Parked skills", "", "| Skill | Size | Limit | Owner of the largest layer |", "|---|---|---|---|"]
    lines += [row(skill, size, inputs.limit, owner) for skill, (size, owner) in (parked or {}).items()]
    return "\n".join(lines) + "\n"


def write_once(path, text):
    """Write a run file once. If the run already has it, the new text must be the same bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as file:  # created here or not at all, so a second resolve never overwrites it
            file.write(text.encode("utf-8"))
    except FileExistsError:
        if path.read_bytes() != text.encode("utf-8"):
            raise ResolveError(f"{path} already exists and differs from this resolve: an input changed during "
                               "the run; start a new run") from None
    return path


def skills_of(manifest):
    """Each release skill as a reach.Skill, from the manifest; a job's `rest` skill keeps the areas `rest`."""
    return {name: reach.Skill(name, tuple(entry["roles"]), (reach.REST,) if entry["rest"] else tuple(entry["areas"]))
            for name, entry in manifest["skills"].items()}


def reached(name, inputs, rules, done):
    """What reaches a run of the skill over the active rules of one stack, in layer order, following what each rule
    replaces in this stack. The `rest` skill also takes, at run time, every area of the job's roles that no other
    skill of the job lists."""
    entry, skills = inputs.manifest["skills"][name], skills_of(inputs.manifest)
    areas = set(entry["areas"])
    if entry["rest"]:
        areas |= reach.areas_of(skills[name], reach.job(inputs.jobs, entry["job"]), skills, rules)
    replaces = {}
    for old, new in done.replaced.items():
        replaces.setdefault(new, []).append(old)
    return reach.reach(rules, entry["roles"], areas, entry["copied-ids"], replaces)


def tightened_by(rule, done):
    return [r.id for r, _, change in done.rules.values() if change == f"Tightens {rule.id}"]


def copy(rule, done):
    """The copy form of a rule written in full. An override carries its Why as the reason (doc 03), and a floor that
    a more specific floor tightens says so."""
    extra = copyform.part_lines(rule, "Why", "Reason for the override") if "Overrides" in rule.parts else []
    if tightened_by(rule, done):
        extra.append(f"- **Tightened by:** {', '.join(tightened_by(rule, done))}")
    return copyform.block(rule, copyform.RULE_PARTS, extra)


def stack_text(name, inputs, rules, done):
    """One stack's section of a rules text, and its full copies as (rule, layer prefix, text)."""
    copied = set(inputs.manifest["skills"][name]["copied-ids"])
    waived = {w["rule"]: w for w in done.waivers if w not in inputs.expired}
    marks, points, full = [], [], []
    for rule in reached(name, inputs, rules, done).rules:
        head = f"- {rule.id} · {rule.title}:"
        if rule.id in done.replaced:
            marks.append(f"{head} replaced by {done.replaced[rule.id]}")
        elif rule.is_decision_point:
            option, source = done.points[rule.id]
            points.append(f"{head} `{option}` (from {source})")
        else:
            if rule.id in waived:
                marks.append(f"{head} waived until {waived[rule.id]['until']}: {waived[rule.id]['reason']}")
            if rule.id not in copied:
                full.append((rule, done.rules[rule.id][1], copy(rule, done)))
            elif tightened_by(rule, done):
                marks.append(f"{head} tightened by {', '.join(tightened_by(rule, done))}")
    floors = [f for f in full if f[0].kind == "floor"]
    others = [f for f in full if f[0].kind != "floor"]
    lines = [f"## Stack: {done.stack}", "", MARKS, ""] + (marks or ["None."]) + ["", POINTS, ""] + (points or ["None."])
    for title, group in ((copyform.FLOORS, floors), (copyform.OTHERS, others)):
        lines += ["", title, ""] + ("\n\n".join(text for _, _, text in group) or "None.").split("\n")
    text = "\n".join(lines) + "\n\n" + copyform.read_back([rule for rule, _, _ in floors + others])
    return text, full


def rules_text(name, inputs, stacks):
    """One skill's rules text and its full copies. stacks is a list of (active rules of a stack, its Resolved)."""
    parts, full = [f"# Rules text: {name}\n\n- **Release:** {inputs.version}\n"], []
    for rules, done in stacks:
        text, copies = stack_text(name, inputs, rules, done)
        parts.append(text)
        full += copies
    return "\n".join(parts), full


def largest_owner(full, inputs):
    """The owner of the layer whose full copies are largest in a rules text, and the sizes per layer and area."""
    sizes = {}
    for rule, layer, text in full:
        sizes[(layer, rule.area)] = sizes.get((layer, rule.area), 0) + reach.size(text)
    by_layer = {}
    for (layer, _), count in sizes.items():
        by_layer[layer] = by_layer.get(layer, 0) + count
    owners = {s.prefix: s.owner for s in inputs.sources}
    largest = max(sorted(by_layer), key=lambda layer: by_layer[layer], default=None)
    return owners.get(largest, "the application owner"), sizes
