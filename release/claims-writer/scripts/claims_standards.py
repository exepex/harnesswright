"""The Standards section of a claims file, checked against the run's own files (doc 06, "Claims").

Standard library only. claims_check.py calls check() with the section's lines, each already matched to one of SHAPES.
One rule: only what the claims writer read or ran itself is `this run`, and each such value must equal the file it
comes from, character for character:
- `rules.md`: the SHA-256 of <run folder>/rules.md;
- Skills run: one entry for this skill, Source `this run`, with the `rulebook-version` and the SHA-256 of
  SKILL_DIR/SKILL.md, `Rules text: not verified` exactly when rules.md holds `not verified:`, and one or more
  read-back blocks, each the block of one of this skill's rules texts in the run folder, in the stack order of
  rules.md. Every other entry is Source `log`: such entries are not checked until the run log records skill runs;
- Changes applied: each line is the ID and title that start a line under "Changes to rules that reach this run" in
  a rules text it quoted;
- Rules applied and Waivers used: `<ID> (this run | log)`, each ID one that SKILL.md, rules.md, a rules text or the
  story names.
Changes applied, Rules applied and Waivers used each hold `None.` alone, or lines and no `None.`.
"""

import re
from pathlib import Path

import copyform
import rulebook
import runfiles

SKILL_DIR = Path(__file__).resolve().parent.parent
HEADINGS = ("Skills run", "Changes applied", "Rules applied", "Waivers used")
FIELDS = ("Source", "Version", "SKILL.md", "Rules text")
SHAPES = [
    ("hash", re.compile(r"- \*\*rules\.md:\*\* (\S+)")),
    ("heading", re.compile(r"### (\S.*)")),
    ("skill", re.compile(r"#### ([a-z0-9]+(?:-[a-z0-9]+)*)")),
    ("field", re.compile(r"- \*\*(Source|Version|SKILL\.md|Rules text):\*\* (\S.*)")),
    ("rule", re.compile(r"- ([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+) \((this run|log)\)")),
    ("change", re.compile(r"- (\S+ · \S.*)")),
    ("none", re.compile(r"None\.")),
]
STACK = re.compile(r"## Stack: (\S+)", re.MULTILINE)


def read_back(text):
    """The read-back block that ends a rules text, markers included, or None."""
    start = text.rfind(copyform.READ_BACK)
    end = text.find(copyform.READ_BACK_END, start)
    return text[start:end + len(copyform.READ_BACK_END)] if start >= 0 and end >= 0 else None


def groups(lines, fails):
    """The section's lines under each heading, the lines before the first under ""; the headings in order."""
    found, current = {"": []}, ""
    for number, name, match in lines:
        if name == "heading":
            current = match.group(1)
            if current not in HEADINGS or current in found:
                fails.append(f"line {number}: Standards headings are {', '.join(HEADINGS)}, once each")
            found[current] = []
        else:
            found[current].append((number, name, match))
    if [h for h in found if h] != list(HEADINGS):
        fails.append(f"Standards: the headings must be {', '.join(HEADINGS)}, in that order")
    return found


def skills(lines, fails):
    """Skills run as {name: (line, {field: value}, [(line, block)])}."""
    found, entry = {}, None
    for number, name, match in lines:
        if name == "skill":
            if match.group(1) in found:
                fails.append(f"line {number}: {match.group(1)} has a second entry under Skills run")
            entry = found[match.group(1)] = (number, {}, [])
        elif entry is None or name not in ("field", "block"):
            fails.append(f"line {number}: not a line Skills run allows here")
        elif name == "field":
            entry[1][match.group(1)] = match.group(2)
        else:
            entry[2].append((number, match))
    for key, (number, fields, _) in found.items():
        if [f for f in FIELDS if f in fields] != list(fields) or not {"Source", "Version", "SKILL.md"} <= set(fields):
            fails.append(f"line {number}: {key} must have Source, Version and SKILL.md, then Rules text if any")
    return found


def items(lines, heading, shape, fails):
    """The lines of Changes applied, Rules applied or Waivers used: `None.` alone, or lines of one shape."""
    names = [name for _, name, _ in lines]
    if names != ["none"] and (not names or any(name != shape for name in names)):
        fails.append(f"{heading}: write `None.` alone when there is nothing, else one line per item")
    return [(number, match) for number, name, match in lines if name == shape]


def check(repo, run, lines, story, fails, notes, skill_dir=None):
    """Check the Standards lines of a claims file whose run folder is `run` (a path from the project root)."""
    skill_dir = Path(skill_dir or SKILL_DIR)
    skill_md = skill_dir / "SKILL.md"
    meta, _ = rulebook.read_frontmatter(skill_md)
    own, version = meta["name"], meta.get("metadata", {}).get("rulebook-version")
    rules_md = repo / run / "rules.md"
    if not rules_md.is_file():
        fails.append(f"Standards: `{run}/rules.md` does not exist; step 1 writes it")
        return
    rules_text = rules_md.read_text(encoding="utf-8")
    found = groups(lines, fails)
    head = found[""]
    if [name for _, name, _ in head] != ["hash"]:
        fails.append("Standards: it starts with one line, `- **rules.md:** <hash of rules.md>`")
    elif head[0][2].group(1) != runfiles.sha(rules_md.read_bytes()):
        fails.append(f"line {head[0][0]}: the hash is not the SHA-256 of `{run}/rules.md`")
    order = STACK.findall(rules_text)
    texts = {}
    for path in sorted((repo / run).glob(f"rules-text-{own}.*.md")):
        text = path.read_text(encoding="utf-8")
        texts[path.name[len(f"rules-text-{own}."):-3]] = (text, read_back(text))
    entries = skills(found.get("Skills run", []), fails)
    quoted = check_own(entries.get(own), own, version, skill_md, texts, order, rules_text, fails)
    for key, (number, fields, _) in entries.items():
        if key != own and fields.get("Source") != "log":
            fails.append(f"line {number}: {key}: Source is `log`; only this skill's own run is `this run`")
    if any(key != own for key in entries):
        notes.append("Standards: entries from the run log; the log does not record skill runs yet")
    marks = [line for stack in quoted for line in texts[stack][0].split("\n") if line.startswith("- ")]
    for number, match in items(found.get("Changes applied", []), "Changes applied", "change", fails):
        if not any(line.startswith(f"- {match.group(1)}:") for line in marks):
            fails.append(f"line {number}: not the ID and title of a change line in a rules text you quoted")
    visible = "\n".join([skill_md.read_text(encoding="utf-8"), rules_text, story] + [t for t, _ in texts.values()])
    for heading in ("Rules applied", "Waivers used"):
        for number, match in items(found.get(heading, []), heading, "rule", fails):
            if not re.search(rf"(?<![\w-]){re.escape(match.group(1))}(?![\w-])", visible):
                fails.append(f"line {number}: {match.group(1)} is in no rule source of this run")


def check_own(entry, own, version, skill_md, texts, order, rules_text, fails):
    """This skill's own entry; returns the stacks whose read-back blocks it quotes."""
    if entry is None:
        fails.append(f"Skills run: no entry for {own}, this skill's own run")
        return []
    number, fields, blocks = entry
    wanted = {"Source": "this run", "Version": version, "SKILL.md": runfiles.sha(skill_md.read_bytes())}
    if "not verified:" in rules_text:
        wanted["Rules text"] = "not verified"
    fails += [f"line {number}: {own}: {key} must be `{value}`" for key, value in wanted.items()
              if fields.get(key) != value]
    if "Rules text" in fields and "Rules text" not in wanted:
        fails.append(f"line {number}: {own}: Rules text is `not verified` only when rules.md says so")
    stacks = []
    for line, block in blocks:
        stack = next((s for s, (_, quote) in texts.items() if quote == block), None)
        if stack is None or stack in stacks:
            fails.append(f"line {line}: not the read-back block of one of {own}'s rules texts, quoted once exactly")
        else:
            stacks.append(stack)
    if not blocks:
        fails.append(f"line {number}: {own} quotes no read-back block")
    rank = [order.index(s) if s in order else len(order) for s in stacks]
    if rank != sorted(rank):
        fails.append(f"line {number}: {own}: the read-back blocks are not in the stack order of rules.md")
    return stacks
