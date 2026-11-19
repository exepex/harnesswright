"""Round results: what `evals/results/<skill>.json` keeps of a finished round (doc 11, Store), so that the label of
each skill on each host can be checked against the round's archive.

One rule: a results entry is a copy, never a new judgement. For each skill the round labelled, it keeps the round's
label file entry for every host whole (`labels.py`), with the file's reference host, price date and thresholds, and
what names the round exactly: its name, attempt, commit, the sha256 of its manifest, the measuring kit its manifest
hashed, the hosts its probe gate passed (`ran`), and the file name and sha256 of the round's store archive. The
archive must hold the round's store folder exactly, so anyone with it recomputes each label with `labels.py` at the round's commit. A round is read only when
its last attempt passed every gate and the kit check of that attempt named the manifest's own kit.

- `entries(folder, archive)`: {skill: entry} for the finished round stored in `folder`, archived in `archive`.
- `merge(current, skill, entry)`: the results file `current` (or None) with `entry` in it. An entry for the same
  round is replaced; other rounds are kept, each listed apart, never combined. Labels from the phase 2 runner stay,
  under `phase_2_runner`, for each host no round of this harness has run yet.
- `write(path, data)`: the results file, one line per field of each host entry, so a round stays short.

Standard library only.
"""

import hashlib
import json
import tarfile
from pathlib import Path

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
    """The paths of the round's last attempt record and its label file. That attempt must have passed every gate."""
    attempts = sorted(Path(folder, "attempts").glob("*.json"))
    if not attempts:
        raise ResultsError(f"{folder}: the round has no attempt")
    attempt = _read(attempts[-1])
    gates = attempt.get("gates") or []
    if not gates or gates[-1].get("gate") != "label" or not all(g.get("passed") for g in gates):
        raise ResultsError(f"{attempts[-1]}: the last attempt did not pass every gate through the label gate")
    return attempts[-1], Path(folder, "labels", attempts[-1].name)


def _folder_files(folder):
    """{path in the round's folder: sha256} of every file under `folder`. A link is refused."""
    found = {}
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ResultsError(f"{path}: a round's store holds no links")
        if path.is_file():
            found[path.relative_to(folder).as_posix()] = _sha256(path)
    return found


def _archive_files(archive, round_name):
    """{path in the round's folder: sha256} of every file the tar file `archive` holds under `<round>/`."""
    found = {}
    try:
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                inside = member.name.startswith(f"{round_name}/") or member.name == round_name
                if not inside or not (member.isfile() or member.isdir()):
                    raise ResultsError(f"{archive}: {member.name} is not a file or folder of round {round_name}")
                if member.isfile():
                    digest, handle = hashlib.sha256(), tar.extractfile(member)
                    for block in iter(lambda: handle.read(1 << 20), b""):
                        digest.update(block)
                    found[member.name[len(round_name) + 1:]] = digest.hexdigest()
    except (OSError, tarfile.TarError) as error:
        raise ResultsError(f"{archive}: not the archive of round {round_name}: {error}") from None
    return found


def entries(folder, archive):
    """{skill: results entry} of the finished round in `folder`, whose store archive is the tar file `archive`.

    One rule: the archive holds the round's store folder exactly, every file with the same bytes and no other, so
    the archive named holds everything that recomputes each label (its runs, checks and grades too)."""
    folder, archive = Path(folder), Path(archive)
    attempt_path, labels_path = finished(folder)
    try:
        manifest = (folder / "manifest.json").read_bytes()
        record, attempt, labels = json.loads(manifest), _read(attempt_path), _read(labels_path)
    except (OSError, ValueError) as error:
        raise ResultsError(f"{folder}: a round file cannot be read: {error}") from None
    kit = next(g for g in attempt["gates"] if g["gate"] == "kit check")["outcome"].get("approved")
    if kit != record["kit"]:
        raise ResultsError(f"{folder}: its kit check named kit {kit}, not the manifest's {record['kit']}")
    held, archived = _folder_files(folder), _archive_files(archive, record["round"])
    differ = sorted(set(held) ^ set(archived) | {p for p in set(held) & set(archived) if held[p] != archived[p]})
    if differ:
        raise ResultsError(f"{archive}: not round {record['round']}'s store folder byte for byte; "
                           f"{len(differ)} file(s) missing or changed, such as {', '.join(differ[:3])}")
    ran = next(g for g in attempt["gates"] if g["gate"] == "probe")["outcome"]["passed"]  # the hosts it ran
    common = {"round": record["round"], "attempt": labels["attempt"], "commit": labels["commit"],
              "manifest_sha256": hashlib.sha256(manifest).hexdigest(), "kit": record["kit"], "ran": ran,
              "archive": {"file": archive.name, "sha256": _sha256(archive)},
              **{key: labels[key] for key in ("reference", "prices", "thresholds")}}
    return {skill: {**common, "hosts": hosts} for skill, hosts in sorted(labels["skills"].items())}


def _order(entry):
    """Rounds in the order they were run: by name, its trailing number read as a number (x-8 before x-10)."""
    stem, _, number = entry["round"].rpartition("-")
    return (stem, int(number)) if number.isdigit() else (entry["round"], -1)


def merge(current, skill, entry):
    """The results file of `skill` with `entry` in it (see the module)."""
    current = current or {}
    if current and current.get("skill", current.get("skill_name")) != skill:
        raise ResultsError(f"the results file is not {skill}'s")
    rounds = [r for r in current.get("rounds", []) if r["round"] != entry["round"]] + [entry]
    rounds.sort(key=_order)
    old = current.get("phase_2_runner", current.get("hosts", []))  # the phase 2 runner's own format
    measured = {host for r in rounds for host in r["ran"]}  # a host the round planned but did not run keeps it
    data = {"skill": skill, "rounds": rounds}
    kept = [h for h in old if h["host"] not in measured]
    return {**data, "phase_2_runner": kept} if kept else data


def write(path, data):
    """Write `data` with each host entry's fields one to a line."""
    lines = ["{", f'  "skill": {json.dumps(data["skill"])},', '  "rounds": [']
    for n, entry in enumerate(data["rounds"]):
        lines.append("    {")
        for key in ("round", "attempt", "commit", "manifest_sha256", "kit", "ran", "archive", "not_run", "reference",
                    "prices", "thresholds"):
            if key not in entry:  # `not_run` is only in entries written before situations were labelled
                continue
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
