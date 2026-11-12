"""Codex's session files, which its adapter reads (adapter.py): every thread of a run, sub-agents included, writes
one in the run's home, with each finished item and the thread's running token count in full."""

import json
from pathlib import Path

# The host's usage field of each neutral count (host.TOKENS). Its input counts cached input.
USAGE = (("input", "input_tokens"), ("cache read", "cached_input_tokens"),
         ("cache write", "cache_write_input_tokens"), ("output", "output_tokens"))


def threads(home):
    """The records of each thread's session file, one list per thread."""
    for path in sorted(Path(home).glob(".codex/sessions/**/rollout-*.jsonl")):
        records = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and isinstance(record.get("payload"), dict):
                records.append(record)
        yield records


def tokens(stdout, home):
    """The host's own token counts by model, or None when no thread reported one: each thread's last token count,
    its running total, under the model of the thread's last turn, summed over the threads of each model."""
    found = {}
    for records in threads(home):
        model = total = None
        for record in records:
            payload = record["payload"]
            if record.get("type") == "turn_context" and isinstance(payload.get("model"), str) and payload["model"]:
                model = payload["model"]
            info = payload.get("info") if payload.get("type") == "token_count" else None
            if isinstance(info, dict) and isinstance(info.get("total_token_usage"), dict):
                total = info["total_token_usage"]
        if total is not None and "input_tokens" in total:
            counts = found.setdefault(model or "unknown model", {name: 0 for name, _ in USAGE})
            for name, field in USAGE:
                counts[name] += total.get(field, 0)
    return found or None
