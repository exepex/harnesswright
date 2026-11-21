"""Why an attempt ended (doc 12, Why an attempt ended): every attempt record says why, before the process exits.

One rule: an attempt record says why it ended in one field, `ended` ({"reason", "at"}), written once, through
`end`, whatever ended it: every gate passed, a gate stopped the round, an error, an exit, or a caught signal
(`signals`): an interrupt (SIGINT), or the SIGTERM or SIGHUP that a tool's time limit or a closed terminal sends,
unless the process ignores it. A signal's reason is written as the signal arrives, before anything unwinds, so a
kill that follows during the cleanup cannot lose it. Only an end no process can catch, such as SIGKILL or a lost
machine, leaves no reason: a resumed round prints the last attempt's reason or that it has none (`resumed`), and the
label file names every attempt with no recorded reason (`unrecorded`).

A record written before `ended` existed is read by its gates (`reason`): a stopped gate's reason, or every gate
passed when its label gate passed. Anything else, an empty or unreadable record too, has no recorded reason.

The attempts of a round have one order, the order they started, read through one function (`attempts`) by every
reader of the last or the latest attempt. An attempt is named by its number (`claim`): one more than the last
numbered attempt, taken by exclusive create, so no two attempts share one and number order is start order whatever
the clock's resolution. An attempt of an older store, named by its start time to the second and a random suffix,
comes before every numbered one, in name order; two of those started in the same second have no known order.

Standard library only.
"""

import contextlib
import datetime
import json
import os
import re
import signal

PASSED = "passed every gate"
_WRITING = set()  # the ids of the attempts whose reason `end` is writing now
CAUGHT = ("SIGINT", "SIGTERM", "SIGHUP")
NUMBERED = re.compile(r"[0-9]+")  # the name of an attempt `claim` made


class Ended(BaseException):
    """A caught signal that ended the attempt. Not an Exception, so no gate takes it for a failure of its own."""


def end(path, attempt, reason, quiet):
    """Write `reason`, scrubbed by `quiet`, as why `attempt` ended, to its record at `path`. The first reason
    written stands: a later call changes nothing, and one made while a write is under way does nothing (`ending`).
    A write that failed records nothing, so a later call can still write its reason."""
    if ending(attempt):
        return
    _WRITING.add(id(attempt))
    try:
        at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        ended = {"reason": quiet(reason), "at": at}
        fresh = path.with_name(f".{path.name}.ended")  # never the file of a write the signal cut short
        fresh.write_text(quiet(json.dumps({**attempt, "ended": ended}, indent=1, sort_keys=True)) + "\n")
        os.replace(fresh, path)
        attempt["ended"] = ended
    finally:
        _WRITING.discard(id(attempt))


def ending(attempt):
    """Whether `attempt` has its reason written, or one is being written now."""
    return "ended" in attempt or id(attempt) in _WRITING


@contextlib.contextmanager
def signals(path, attempt, during, quiet):
    """While the block runs, a caught signal writes why `attempt` ended (`end`), naming the gate `during()` gives,
    and raises `Ended`. Once the attempt is ending, a later signal is let pass, so the reason being written is not
    cut short. A signal the process ignores, such as SIGHUP under `nohup`, stays ignored. Outside the main thread no
    signal can be caught, and the block runs without."""
    def caught(number, frame):
        if ending(attempt):
            return
        end(path, attempt, f"stopped by {signal.Signals(number).name} during the {during()} gate", quiet)
        raise Ended(attempt["ended"]["reason"])

    before = {}
    try:
        for name in CAUGHT:
            if hasattr(signal, name) and signal.getsignal(getattr(signal, name)) != signal.SIG_IGN:
                before[name] = signal.signal(getattr(signal, name), caught)
    except ValueError:  # not the main thread
        pass
    try:
        yield
    finally:
        for name, handler in before.items():
            signal.signal(getattr(signal, name), handler)


def reason(path):
    """Why the attempt recorded at `path` ended, or None when its record does not say."""
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    if isinstance(record.get("ended"), dict):
        return record["ended"].get("reason")
    last = (record.get("gates") or [{}])[-1]
    if last.get("passed") is False:
        return f"stopped at the {last.get('gate')} gate: {last.get('reason')}"
    return PASSED if (last.get("gate"), last.get("passed")) == ("label", True) else None


def attempts(folder):
    """The attempt records in `folder` in the order they started: every attempt of an older store first, in name
    order, then every numbered attempt, in number order. A name that starts with a dot is a write under way."""
    def order(path):
        return (1, int(path.stem), path.stem) if NUMBERED.fullmatch(path.stem) else (0, 0, path.stem)

    if not folder.is_dir():
        return []
    return sorted((p for p in folder.glob("*.json") if not p.name.startswith(".")), key=order)


def claim(folder):
    """The path of a new, empty attempt record in `folder`, named by the next number: one more than the last
    numbered attempt's, the next free one when another process took it first."""
    folder.mkdir(parents=True, exist_ok=True)
    numbered = [int(p.stem) for p in attempts(folder) if NUMBERED.fullmatch(p.stem)]
    number = max(numbered, default=0) + 1
    while True:
        path = folder / f"{number:06d}.json"
        try:
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))  # only where no entry has its name
            return path
        except FileExistsError:
            number += 1


def resumed(folder, name):
    """The lines a run of round `name` prints before it starts: why its last attempt in `folder` ended, if any."""
    found = attempts(folder)
    if not found:
        return []
    why = reason(found[-1])
    said = f"ended: {why}" if why else "has no recorded reason"
    return [f"round {name}: resuming; the last attempt {found[-1].stem} {said}"]


def unrecorded(folder, attempt):
    """The names of the attempts in `folder`, other than `attempt`, with no recorded reason."""
    return [p.stem for p in attempts(folder) if p.stem != attempt and reason(p) is None]
