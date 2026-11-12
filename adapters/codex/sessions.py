"""Codex's session files, which its adapter reads (adapter.py): every thread of a run, sub-agents included, writes
one in the run's home, with each finished item and the usage of each model response."""

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
    """The host's own token counts by model, or None when no response reported one. Each model response leaves one
    usage record with its own usage, its thread and its turn; a forked sub-agent copies its parent's history but not
    these records, and a copy would be counted once anyway. Each response counts once, under the model of its turn."""
    models, used = {}, {}  # turn id: model; (thread, response): (turn id, usage)
    for records in threads(home):
        for record in records:
            payload = record["payload"]
            if record.get("type") == "turn_context" and isinstance(payload.get("model"), str) and payload["model"]:
                models[payload.get("turn_id")] = payload["model"]
            elif record.get("type") == "token_usage_record" and isinstance(payload.get("usage"), dict):
                used[(payload.get("thread_id"), payload.get("response_id"))] = (payload.get("turn_id"),
                                                                                payload["usage"])
    found = {}
    for turn, usage in used.values():
        counts = found.setdefault(models.get(turn) or "unknown model", {name: 0 for name, _ in USAGE})
        for name, field in USAGE:
            counts[name] += usage.get(field, 0)
    return found or None
