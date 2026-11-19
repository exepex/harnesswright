"""Round results: what `evals/results/<skill>.json` keeps of a finished round (doc 11, Store), so that the label of
each skill on each host can be checked against the round's archive.

One rule: a results entry is a copy, never a new judgement. For each skill the round labelled, it keeps the round's
label file entry for every host whole (`labels.py`), with the file's reference host, price date and thresholds, and
what names the round exactly: its name, attempt, commit, the sha256 of its manifest, the measuring kit its manifest
hashed, and the file name and sha256 of the round's store archive. Anyone with the archive recomputes each label with `labels.py` at the round's commit. A round is read only
when its last attempt passed every gate and the kit check of that attempt named the manifest's own kit.

- `entries(folder, archive)`: {skill: entry} for the finished round stored in `folder`, archived in `archive`.
- `merge(current, skill, entry)`: the results file `current` (or None) with `entry` in it. An entry for the same
  round is replaced; other rounds are kept, each listed apart, never combined. Labels from the phase 2 runner stay,
  under `phase_2_runner`, for each host no round of this harness has labelled yet.
- `write(path, data)`: the results file, one line per field of each host entry, so a round stays short.

Standard library only.
"""

import hashlib
import json
import tarfile
from pathlib import Path

NOT_RUN = ["skill-fault gate"]  # gates doc 11 names that no round could run yet; never read as a gap


class ResultsError(ValueError):
    """The round is not a finished round this module can copy. Nothing is written."""


def _read(path):
    try:
        return json.loads(Path(path).read_bytes())
    except (OSError, ValueError) as error:
        raise ResultsError(f"{path}: cannot be read: {error}") from None


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def finished(folder):
    """(attempt record, label file) of the round's last attempt, which must have passed every gate."""
    attempts = sorted(Path(folder, "attempts").glob("*.json"))
    if not attempts:
        raise ResultsError(f"{folder}: the round has no attempt")
    attempt = _read(attempts[-1])
    gates = attempt.get("gates") or []
    if not gates or gates[-1].get("gate") != "label" or not all(g.get("passed") for g in gates):
        raise ResultsError(f"{attempts[-1]}: the last attempt did not pass every gate through the label gate")
    return attempt, _read(Path(folder, "labels", attempts[-1].name))


def entries(folder, archive):
    """{skill: results entry} of the finished round in `folder`, whose store archive is the tar file `archive`."""
    folder, archive = Path(folder), Path(archive)
    manifest = Path(folder, "manifest.json").read_bytes()
    record = json.loads(manifest)
    attempt, labels = finished(folder)
    kit = next(g for g in attempt["gates"] if g["gate"] == "kit check")["outcome"].get("approved")
    if kit != record["kit"]:
        raise ResultsError(f"{folder}: its kit check named kit {kit}, not the manifest's {record['kit']}")
    try:
        with tarfile.open(archive) as tar:
            member = tar.extractfile(f"{record['round']}/manifest.json")
            archived = member.read() if member else None
    except (OSError, KeyError, tarfile.TarError) as error:
        raise ResultsError(f"{archive}: not the archive of round {record['round']}: {error}") from None
    if archived != manifest:
        raise ResultsError(f"{archive}: its manifest is not the round's")
    common = {"round": record["round"], "attempt": labels["attempt"], "commit": labels["commit"],
              "manifest_sha256": hashlib.sha256(manifest).hexdigest(), "kit": record["kit"],
              "archive": {"file": archive.name, "sha256": _sha256(archive)}, "not_run": NOT_RUN,
              **{key: labels[key] for key in ("reference", "prices", "thresholds")}}
    return {skill: {**common, "hosts": hosts} for skill, hosts in sorted(labels["skills"].items())}


def merge(current, skill, entry):
    """The results file of `skill` with `entry` in it (see the module)."""
    current = current or {}
    if current and current.get("skill", current.get("skill_name")) != skill:
        raise ResultsError(f"the results file is not {skill}'s")
    rounds = [r for r in current.get("rounds", []) if r["round"] != entry["round"]] + [entry]
    rounds.sort(key=lambda r: r["round"])
    old = current.get("phase_2_runner", current.get("hosts", []))  # the phase 2 runner's own format
    measured = {host for r in rounds for host in r["hosts"]}
    data = {"skill": skill, "rounds": rounds}
    kept = [h for h in old if h["host"] not in measured]
    return {**data, "phase_2_runner": kept} if kept else data


def write(path, data):
    """Write `data` with each host entry's fields one to a line."""
    lines = ["{", f'  "skill": {json.dumps(data["skill"])},', '  "rounds": [']
    for n, entry in enumerate(data["rounds"]):
        lines.append("    {")
        for key in ("round", "attempt", "commit", "manifest_sha256", "kit", "archive", "not_run", "reference",
                    "prices", "thresholds"):
            lines.append(f"      {json.dumps(key)}: {json.dumps(entry[key], sort_keys=True)},")
        lines.append('      "hosts": {')
        for m, (host, fields) in enumerate(sorted(entry["hosts"].items())):
            lines.append(f"        {json.dumps(host)}: {{")
            body = [f"          {json.dumps(k)}: {json.dumps(v, sort_keys=True)}" for k, v in sorted(fields.items())]
            lines.append(",\n".join(body))
            lines.append("        }" + ("," if m < len(entry["hosts"]) - 1 else ""))
        lines.append("      }")
        lines.append("    }" + ("," if n < len(data["rounds"]) - 1 else ""))
    lines.append("  ]" + ("," if "phase_2_runner" in data else ""))
    if "phase_2_runner" in data:
        lines.append(f'  "phase_2_runner": {json.dumps(data["phase_2_runner"], sort_keys=True)}')
    lines.append("}")
    text = "\n".join(lines) + "\n"
    if json.loads(text) != data:  # the layout never changes what is written
        raise ResultsError(f"{path}: the written layout does not read back as the results")
    Path(path).write_text(text)
    return path


def publish(folder, archive, results_dir):
    """Merge the round in `folder` into each labelled skill's results file in `results_dir`. Return the paths."""
    written = []
    for skill, entry in entries(folder, archive).items():
        path = Path(results_dir) / f"{skill}.json"
        current = _read(path) if path.exists() else None
        written.append(write(path, merge(current, skill, entry)))
    return written
