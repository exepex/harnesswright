"""The Standards section of a claims file, checked against the run's own files (doc 06, "Claims").

Standard library only. claims_check.py calls check() with the section's lines, each already matched to one of SHAPES.
One rule: every `this run` value equals what the run's files give, character for character, and every list equals its
source both ways: nothing left out and nothing added.
- `rules.md`: the SHA-256 of <run folder>/rules.md;
- Skills run: one entry for this skill, Source `this run`, with the `rulebook-version` and the SHA-256 of
  SKILL_DIR/SKILL.md, `Rules text: not verified` exactly when rules.md holds a line `not verified: <reason>`, and one
  or more read-back blocks, each the block of one of this skill's rules texts in the run folder, in the stack order
  of rules.md;
- Changes applied: the ID and title of each line under "Changes to rules that reach this run" and of each decision
  point a layer binds (not `from default`), in the rules texts quoted;
- Waivers used: each waiver of the story's `waivers`, and each that rules.md marks `applied` in the stacks quoted;
- Rules applied: each ID one that SKILL.md, rules.md, a rules text or the story names (what the agent applied is
  not in a file, so this list is checked one way only).
A `log` entry or line is checked only once the run log records skill runs; until then <run folder>/log.md must exist
for one to be written. Changes applied, Rules applied and Waivers used each hold `None.` alone, or lines and no `None.`.
"""

import re
from pathlib import Path

import copyform
import rulebook
import runfiles

SKILL_DIR = Path(__file__).resolve().parent.parent
HEADINGS = ("Skills run", "Changes applied", "Rules applied", "Waivers used")
FIELDS = ("Source", "Version", "SKILL.md", "Rules text")
RULE_ID = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+"
SHAPES = [
    ("hash", re.compile(r"- \*\*rules\.md:\*\* (\S+)")),
    ("heading", re.compile(r"### (\S.*)")),
    ("skill", re.compile(r"#### ([a-z0-9]+(?:-[a-z0-9]+)*)")),
    ("field", re.compile(r"- \*\*(Source|Version|SKILL\.md|Rules text):\*\* (\S.*)")),
    ("rule", re.compile(rf"- ({RULE_ID}) \((this run|log)\)")),
    ("change", re.compile(r"- (\S+ · \S.*)")),
    ("none", re.compile(r"None\.")),
]
STACK = re.compile(r"## Stack: (\S+)", re.MULTILINE)
NOT_VERIFIED = re.compile(r"^not verified: \S", re.MULTILINE)
MARK = re.compile(r"- (\S+ · .+?): (?:replaced by|waived until|tightened by) \S.*")
POINT = re.compile(r"- (\S+ · .+): `[^`]*` \(from (?!default\))[^)]*\)")
STORY_WAIVER = re.compile(rf" *(?:- +)?rule: *({RULE_ID}) *(?:#.*)?")  # the one `rule:` key of the frontmatter
APPLIED = re.compile(rf"\| ({RULE_ID}) \|.*\| applied \|")


class InputError(Exception):
    """A run file the check cannot read: claims_check stops with exit 2."""


def load(path, what):
    """A file's bytes and text."""
    try:
        data = path.read_bytes()
        return data, data.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise InputError(f"{what} {path}: cannot be read ({type(error).__name__})") from None


def read_back(text):
    """The read-back block that ends a rules text, markers included, or None."""
    start = text.rfind(copyform.READ_BACK)
    end = text.find(copyform.READ_BACK_END, start)
    return text[start:end + len(copyform.READ_BACK_END)] if start >= 0 and end >= 0 else None


def section(text, heading):
    """The lines under each `### ` heading of a file with this title, each up to the next heading."""
    found, inside = [], False
    for line in text.split("\n"):
        if line.startswith("#"):
            inside = line == heading
        elif inside:
            found.append(line)
    return found


def changes(text):
    """The ID and title of each change and each bound decision point of a rules text."""
    return [m.group(1) for pattern, heading in ((MARK, runfiles.MARKS), (POINT, runfiles.POINTS))
            for line in section(text, heading) if (m := pattern.fullmatch(line))]


def waivers(rules_text, story, stacks):
    """The waivers a run uses: the story's, and those rules.md marks `applied` in the stacks quoted."""
    lines = story.split("\n")
    front = lines[1:lines.index("---", 1)] if lines[0] == "---" and "---" in lines[1:] else []
    shapes = [re.fullmatch(r"waivers: *(\[\])? *(?:#.*)?", line) for line in front if line.startswith("waivers:")]
    rules = [line for line in front if re.match(r" *(?:- +)?rule:", line)]
    if any(m is None for m in shapes) or any(not STORY_WAIVER.fullmatch(line) for line in rules):
        raise InputError("story: `waivers` must be `[]` or the block form of contracts/story.md, IDs unquoted")
    found = [STORY_WAIVER.fullmatch(line).group(1) for line in rules]
    parts = re.split(r"^## Stack: (\S+)$", rules_text, flags=re.MULTILINE)
    bodies = [body for stack, body in zip(parts[1::2], parts[2::2]) if stack in stacks]
    found += [m.group(1) for body in bodies for line in section(body, "### Waivers") if (m := APPLIED.fullmatch(line))]
    return found


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
            if match.group(1) in entry[1]:
                fails.append(f"line {number}: {match.group(1)} appears twice in one entry")
            entry[1][match.group(1)] = match.group(2).strip("`")
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


def equal(heading, listed, wanted, fails, extras=True):
    """A list equals its source: each wanted item listed once, and (with extras) nothing else."""
    seen = []
    for number, value in listed:
        if value in seen:
            fails.append(f"line {number}: {value} is listed twice")
        elif value not in wanted and extras:
            fails.append(f"line {number}: {value} is not in the {heading.lower()} the run's files give")
        seen.append(value)
    fails += [f"{heading}: {value} is missing" for value in dict.fromkeys(wanted) if value not in seen]


def check(repo, run, lines, story, fails, notes, skill_dir=None):
    """Check the Standards lines of a claims file whose run folder is `run` (a path from the project root)."""
    skill_dir = Path(skill_dir or SKILL_DIR)
    skill_md = skill_dir / "SKILL.md"
    skill_bytes, skill_text = load(skill_md, "SKILL.md")
    meta, _ = rulebook.read_frontmatter(skill_md)
    own, version = meta["name"], meta.get("metadata", {}).get("rulebook-version")
    rules_md = repo / run / "rules.md"
    if not rules_md.is_file():
        fails.append(f"Standards: `{run}/rules.md` does not exist; step 1 writes it in the run folder, and the "
                     "claims file is `<run folder>/claims/<story ID>.md`")
        return
    rules_bytes, rules_text = load(rules_md, "rules.md")
    found = groups(lines, fails)
    head = found[""]
    if [name for _, name, _ in head] != ["hash"]:
        fails.append("Standards: it starts with one line, `- **rules.md:** <hash of rules.md>`")
    elif head[0][2].group(1).strip("`") != runfiles.sha(rules_bytes):
        fails.append(f"line {head[0][0]}: the hash is not the SHA-256 of `{run}/rules.md`")
    texts = {}
    for path in sorted((repo / run).glob(f"rules-text-{own}.*.md")):
        text = load(path, "rules text")[1]
        texts[path.name[len(f"rules-text-{own}."):-3]] = (text, read_back(text))
    entries = skills(found.get("Skills run", []), fails)
    known = check_own(entries.get(own), own, version, runfiles.sha(skill_bytes), texts, rules_text, fails)
    logged = [n for key, (n, _, _) in entries.items() if key != own] + [n for h in ("Rules applied", "Waivers used")
                                                                      for n, name, m in found.get(h, [])
                                                                      if name == "rule" and m.group(2) == "log"]
    for key, (number, fields, _) in entries.items():
        if key != own and fields.get("Source") != "log":
            fails.append(f"line {number}: {key}: Source is `log`; only this skill's own run is `this run`")
    if logged and not (repo / run / "log.md").is_file():
        fails += [f"line {n}: a `log` entry is written only when `{run}/log.md` records it" for n in logged]
    elif logged:
        notes.append("Standards: entries from the run log; the log does not record skill runs yet")
    wanted = [c for stack in known["quoted"] for c in changes(texts[stack][0])]
    listed = [(n, m.group(1)) for n, m in items(found.get("Changes applied", []), "Changes applied", "change", fails)]
    equal("Changes applied", listed, wanted, fails, extras=known["complete"])
    visible = "\n".join([skill_text, rules_text, story] + [t for t, _ in texts.values()])
    for number, match in items(found.get("Rules applied", []), "Rules applied", "rule", fails):
        if not re.search(rf"(?<![\w-]){re.escape(match.group(1))}(?![\w-])", visible):
            fails.append(f"line {number}: {match.group(1)} is in no rule source of this run")
    used = items(found.get("Waivers used", []), "Waivers used", "rule", fails)
    equal("Waivers used", [(n, m.group(1)) for n, m in used if m.group(2) == "this run"],
          waivers(rules_text, story, known["quoted"]), fails, extras=known["complete"])


def check_own(entry, own, version, skill_hash, texts, rules_text, fails):
    """This skill's own entry; returns the stacks whose read-back blocks it quotes, and whether every block matched."""
    if entry is None:
        fails.append(f"Skills run: no entry for {own}, this skill's own run")
        return {"quoted": [], "complete": False}
    number, fields, blocks = entry
    wanted = {"Source": "this run", "Version": version, "SKILL.md": skill_hash}
    by_reading = bool(NOT_VERIFIED.search(rules_text))
    if by_reading:
        wanted["Rules text"] = "not verified"
    fails += [f"line {number}: {own}: {key} must be {value}" for key, value in wanted.items()
              if fields.get(key) != value]
    if "Rules text" in fields and not by_reading:
        fails.append(f"line {number}: {own}: Rules text is `not verified` only when rules.md has a line "
                     "`not verified: <reason>`")
    stacks, complete = [], bool(blocks)
    for line, block in blocks:
        stack = next((s for s, (_, quote) in texts.items() if quote == block), None)
        if stack is None or stack in stacks:
            fails.append(f"line {line}: not the read-back block of one of {own}'s rules texts, quoted once exactly")
            complete = False
        else:
            stacks.append(stack)
    if not blocks:
        fails.append(f"line {number}: {own} quotes no read-back block")
    order = STACK.findall(rules_text)
    rank = [order.index(s) if s in order else len(order) for s in stacks]
    if rank != sorted(rank):
        fails.append(f"line {number}: {own}: the read-back blocks are not in the stack order of rules.md")
    return {"quoted": stacks, "complete": complete}
