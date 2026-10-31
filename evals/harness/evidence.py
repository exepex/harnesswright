"""Evidence: one host-neutral record of each run (doc 11, Evidence).

Each adapter turns its host's events into an action log. Every entry has a `kind` and a `source`: `observed`
when the host reported it, `inferred` when the adapter worked it out, such as a file read parsed from a shell
command. A script check decides only on observed entries (`decidable`); inferred ones go to graders.

The runner adds a world diff and writes the bundle. Graders get the grader view: the bundle without anything the
with-skill overlay added, so they cannot tell the arm. The full bundle is kept for audits and judges.
"""

import json
import re
import shutil
from pathlib import Path

from cases import tree
from lint import shingles

KINDS = ("read", "search", "write", "command", "blocked", "skill_load", "tool")
SOURCES = ("observed", "inferred")
REDACTED = "[REDACTED]"
NEUTRAL_SKILL = "the-skill"
# What graders see of a run record: the outcome and the evidence, never the arm, skills, host, model or timings.
GRADER_FIELDS = ("mode", "final", "failure", "timed_out", "actions", "diff")


class EvidenceError(ValueError):
    """An action log or bundle that breaks the evidence format."""


def validate(log):
    """Raise EvidenceError unless every entry has a known kind and source."""
    for number, entry in enumerate(log):
        if entry.get("kind") not in KINDS:
            raise EvidenceError(f"entry {number}: unknown kind {entry.get('kind')!r}")
        if entry.get("source") not in SOURCES:
            raise EvidenceError(f"entry {number}: source must be observed or inferred")
    return log


def decidable(log):
    """The entries a script check may decide on: observed ones only."""
    return [entry for entry in validate(log) if entry["source"] == "observed"]


def redact(text, secrets):
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    return text


def scrub(value, secrets):
    """`value` with every credential redacted from every string in it, keys included."""
    if isinstance(value, str):
        return redact(value, secrets)
    if isinstance(value, dict):
        return {scrub(key, secrets): scrub(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(item, secrets) for item in value]
    return value


def tokens_in(text, tokens):
    """Every canary token that appears in `text`."""
    return sorted(token for token in tokens if token in text)


def world_diff(before, after_dir, ignore=()):
    """What the run changed in the world: {"added", "changed", "removed"}, each a sorted list of paths.

    `before` is the arm's {path: sha256} map; paths under any prefix in `ignore` (the host's measured
    self-writes and the installed skill copies) are left out.
    """
    after = tree(after_dir, skip=(".git",))

    def kept(path):
        return not any(path == p or path.startswith(p.rstrip("/") + "/") for p in ignore)

    return {"added": sorted(p for p in after if p not in before and kept(p)),
            "changed": sorted(p for p in after if p in before and after[p] != before[p] and kept(p)),
            "removed": sorted(p for p in before if p not in after and kept(p))}


def write_bundle(folder, record, world_after, secrets, tokens):
    """Write one run's bundle: `bundle.json` and a copy of the world after the run in `files/`.

    Credential values are redacted before anything is written. Returns the canary tokens found in the record or
    the files, which void the run.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    # Values are redacted before serialization, so JSON escaping cannot hide a credential from the match.
    text = json.dumps(scrub(record, secrets), indent=1, sort_keys=True)
    hits = tokens_in(text, tokens)
    (folder / "bundle.json").write_text(text + "\n")
    files = folder / "files"
    shutil.copytree(world_after, files, symlinks=True, ignore=shutil.ignore_patterns(".git"))
    # A bundle holds no symlinks: each becomes a text file naming its target, so nothing in the bundle can lead
    # outside it or carry an unscrubbed file.
    for path in sorted(files.rglob("*")):
        if path.is_symlink():
            target = str(path.readlink())
            path.unlink()
            path.write_text(f"symlink to {target}\n")
    # Every file is scrubbed as bytes, so a binary artifact cannot carry a credential or hide a canary.
    for path in sorted(files.rglob("*")):
        if path.is_file() and not path.is_symlink():
            data = path.read_bytes()
            clean = data
            for secret in secrets:
                if secret:
                    clean = clean.replace(secret.encode(), REDACTED.encode())
            hits += [token for token in tokens if token.encode() in clean]
            if clean != data:
                path.write_bytes(clean)
    return sorted(set(hits))


def grader_view(bundle_dir, out_dir, overlay_paths, skill_names, rows=(), skill_texts=()):
    """Write the view graders get of a bundle: only the GRADER_FIELDS of its record. The overlay's files and
    index rows are gone from the files and
    the diff. Skill loads, and every action that names an overlay path or whose text holds an 8-word run of the
    skill (`skill_texts`, such as a command that printed SKILL.md), are gone from the action log. Skill names,
    skill paths and the arm are replaced by neutral words everywhere. Call it with the same names for both arms."""
    bundle_dir, out_dir = Path(bundle_dir), Path(out_dir)
    record = json.loads((bundle_dir / "bundle.json").read_text())
    # Allow, never deny: the view holds only these fields, so no record field added later can tell the arm.
    record = {key: record[key] for key in GRADER_FIELDS if key in record}

    def outside(path):
        return not any(path == p or path.startswith(p.rstrip("/") + "/") for p in overlay_paths)

    diff = record.get("diff") or {}
    record["diff"] = {key: [p for p in paths if outside(p)] for key, paths in diff.items()}
    marks = set()
    for text in skill_texts:
        marks |= shingles(text)

    def shows_skill(entry):
        text = json.dumps(entry)
        return any(p in text for p in overlay_paths) or bool(marks & shingles(text))

    record["actions"] = [entry for entry in record.get("actions") or []
                         if entry.get("kind") != "skill_load" and not shows_skill(entry)]
    text = _neutral(json.dumps(record, indent=1, sort_keys=True), overlay_paths, skill_names)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bundle.json").write_text(text + "\n")
    source = bundle_dir / "files"
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source).as_posix()
        if not outside(relative):
            continue
        target = out_dir / "files" / relative
        if path.is_dir() and not path.is_symlink():
            # Empty folders are kept: making a folder can be what the task asked for.
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            lines = [line for line in path.read_text().split("\n") if line not in rows]
            target.write_text(_neutral("\n".join(lines), overlay_paths, skill_names))
        except UnicodeDecodeError:
            shutil.copy2(path, target)
    # A folder on the way to an overlay path that holds nothing else is left out, in both arms alike, so the
    # folders the overlay needed do not show.
    for overlay in overlay_paths:
        for folder in Path(overlay).parents:
            path = out_dir / "files" / folder
            if folder != Path(".") and path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    return out_dir


def _neutral(text, overlay_paths, skill_names):
    for path in sorted(overlay_paths, key=len, reverse=True):
        text = text.replace(path, "skills/" + NEUTRAL_SKILL)
    for name in sorted(skill_names, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(name)}\b", NEUTRAL_SKILL, text)
    return re.sub(r"\b(with|without)_skill\b", "arm", text)
