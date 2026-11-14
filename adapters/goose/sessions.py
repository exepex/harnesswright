"""goose's session store, which its adapter reads (adapter.py). goose keeps every session of a run, sub-agents
included, in one SQLite file in the run's home, even with `--no-session`: each session's working folder, every
message of every session in the order goose stored it, and one usage row for each model response, under the model
that response reported."""

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

STORE = Path(".local") / "share" / "goose" / "sessions" / "sessions.db"
# The store's usage columns for each neutral count (host.TOKENS). goose's input counts cached input.
USAGE = (("input", "input_tokens"), ("cache read", "cache_read_tokens"), ("cache write", "cache_write_tokens"),
         ("output", "output_tokens"))


class Unreadable(Exception):
    """The store is missing or not in the form this adapter reads."""


def read(home):
    """{"sessions": {id: working folder}, "messages": [(session, role, content)], "usage": [(model, counts)]} from
    a copy of the store, so the run's own files are never changed by reading them. Raise Unreadable when there is no
    store or it is in another form."""
    store = Path(home) / STORE
    if not store.is_file():
        raise Unreadable("no session store")
    with tempfile.TemporaryDirectory() as folder:
        for suffix in ("", "-wal", "-shm"):  # the store and its write-ahead log, which may hold its last writes
            if Path(f"{store}{suffix}").is_file():
                shutil.copyfile(f"{store}{suffix}", Path(folder) / f"sessions.db{suffix}")
        try:
            with closing(sqlite3.connect(Path(folder) / "sessions.db")) as db:
                sessions = dict(db.execute("SELECT id, working_dir FROM sessions"))
                messages = db.execute("SELECT session_id, role, content_json FROM messages ORDER BY id").fetchall()
                usage = db.execute("SELECT model, " + ", ".join(column for _, column in USAGE)
                                   + " FROM usage_ledger ORDER BY id").fetchall()
        except sqlite3.Error as error:
            raise Unreadable(f"session store: {error}") from None
    found = []
    for session, role, content in messages:
        try:
            parts = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            raise Unreadable("a message is not JSON") from None
        if session not in sessions or not isinstance(parts, list):
            raise Unreadable("a message of no session, or not a list of parts")
        found.append((session, role, [part for part in parts if isinstance(part, dict)]))
    return {"sessions": sessions, "messages": found,
            "usage": [(model, dict(zip((name for name, _ in USAGE), counts))) for model, *counts in usage]}


def tokens(stdout, home):
    """The host's own token counts by model, or None when it reported none. Each model response leaves one usage
    row under the model it reported, sub-agents' and compaction's included, so each is counted once. A row missing a
    count leaves the run's counts unknown: a count goose did not report is missing, never estimated."""
    try:
        rows = read(home)["usage"]
    except Unreadable:
        return None
    totals = {}
    for model, counts in rows:
        if not isinstance(model, str) or not model or any(
                not isinstance(count, int) or isinstance(count, bool) or count < 0 for count in counts.values()):
            return None
        for name, count in counts.items():
            totals.setdefault(model, dict.fromkeys(counts, 0))[name] += count
    return totals or None


def _result(response):
    """(worked, text, structured) of a tool response: whether the call worked, its text and its structured part."""
    result = response.get("toolResult") if isinstance(response, dict) else None
    value = result.get("value") if isinstance(result, dict) else None
    if not isinstance(value, dict) or result.get("status") != "success":
        error = result.get("error") if isinstance(result, dict) else None
        return False, str(error.get("message", error) if isinstance(error, dict) else error or ""), {}
    text = "\n".join(str(part.get("text", "")) for part in value.get("content") or []
                     if isinstance(part, dict) and part.get("type") == "text")
    structured = value.get("structuredContent")
    return not value.get("isError"), text, structured if isinstance(structured, dict) else {}


def _path(folder, path):
    """A path a tool was given, as the path it reaches: relative to the session's working folder."""
    return os.path.normpath(os.path.join(folder, path)) if folder else os.path.normpath(path)


def _entries(name, arguments, response, folder):
    """The log entries of one tool call by `name` with `arguments`, given its `response` (None when it has none)."""
    worked, text, structured = _result(response) if response is not None else (False, "", {})
    if name == "shell":
        code = structured.get("exit_code")
        output = "\n".join(str(structured[key]) for key in ("stdout", "stderr") if structured.get(key)) or text
        return [{"kind": "command", "source": "observed", "command": str(arguments.get("command", "")),
                 "exit_code": code if isinstance(code, int) and not isinstance(code, bool) else None,
                 "output": output}]
    if name in ("write", "edit"):
        path = _path(folder, str(arguments.get("path", "")))
        if not worked:
            return [{"kind": "failed", "source": "observed", "action": f"{name}: {path}", "path": path,
                     "reason": text}]
        content = arguments.get("content") if name == "write" else None
        digest = hashlib.sha256(content.encode()).hexdigest() if isinstance(content, str) else None
        return [{"kind": "write", "source": "observed", "path": path, "sha256": digest}]
    if name in ("tree", "read_image"):
        return [{"kind": "read", "source": "observed", "path": _path(folder, str(arguments.get("path") or "."))}]
    if name == "load" and arguments.get("source"):
        return [{"kind": "read", "source": "observed", "path": str(arguments["source"])}]
    if name == "load_skill" and worked:
        return [{"kind": "skill", "source": "observed", "name": str(arguments.get("name", ""))}]
    if name == "delegate":
        task = arguments.get("instructions") or arguments.get("source") or arguments.get("resume") or ""
        return [{"kind": "agent", "source": "observed", "task": str(task)}]
    return []  # a tool that only waits or hands back an answer, or one goose would not run (exposure)


def action_log(stdout, home):
    """The action log of every session of the run, sub-agents included, in the order goose stored their messages:
    each tool call, at its request, with what its response says, and each answer the model gave. A call whose
    request did not parse ran nothing."""
    try:
        store = read(home)
    except Unreadable:
        return []
    responses = {(session, part.get("id")): part for session, role, parts in store["messages"] for part in parts
                 if part.get("type") == "toolResponse"}
    log = []
    for session, role, parts in store["messages"]:
        if role != "assistant":
            continue
        text = "".join(str(part.get("text", "")) for part in parts if part.get("type") == "text")
        if text:
            log.append({"kind": "message", "source": "observed", "text": text})
        for part in parts:
            call = part.get("toolCall") if part.get("type") == "toolRequest" else None
            value = call.get("value") if isinstance(call, dict) and call.get("status") == "success" else None
            if isinstance(value, dict) and isinstance(value.get("name"), str):
                arguments = value.get("arguments") if isinstance(value.get("arguments"), dict) else {}
                log += _entries(value["name"], arguments, responses.get((session, part.get("id"))),
                                store["sessions"].get(session))
    return log
