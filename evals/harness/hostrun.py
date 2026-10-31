"""Run a host once inside its containment: audit first, then the host, then its action log.

A failed audit raises ContainmentError before the host starts: the run is voided and the round stops.
"""

import subprocess
import time

from contain import ContainmentError  # noqa: F401  (re-exported for callers)
from evidence import tokens_in, validate


class HostRun:
    """What one host run produced, before it is written as a bundle."""

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def record(self):
        return {key: getattr(self, key) for key in ("mode", "returncode", "timed_out", "failure", "model",
                                                     "seconds", "actions", "exposed_skills", "final", "leaks")}


def run(adapter, contain, prompt, model=None, deny=(), timeout=900):
    """Run `prompt` on the host of `adapter` in `contain`. Raises ContainmentError when the audit fails."""
    contain.prepared = list(adapter.prepare_home(contain.home, deny) or [])
    audit = contain.audit(adapter.CLI)
    host = adapter.command(contain.mode, contain.world, contain.scratch, model, deny)
    started = time.monotonic()
    timed_out = False
    try:
        done = subprocess.run(contain.jail(host), input=prompt, capture_output=True, text=True, env=contain.env,
                              timeout=timeout)
        stdout, stderr, code = done.stdout, done.stderr, done.returncode
    except subprocess.TimeoutExpired as expired:
        stdout = _text(expired.stdout)
        stderr = _text(expired.stderr)
        code, timed_out = None, True
    events = adapter.parse_events(stdout)
    # Canaries are looked for in the whole raw output, before the action log bounds long command output.
    leaks = tokens_in(stdout + stderr, contain.canaries)
    return HostRun(leaks=leaks, mode=contain.mode, events=events, stderr=stderr, returncode=code,
                   timed_out=timed_out,
                   failure=adapter.failure(events, code, timed_out, contain.mode),
                   model=adapter.resolved_model(events) or model, seconds=round(time.monotonic() - started, 1),
                   actions=validate(adapter.actions(events, stderr)),
                   exposed_skills=adapter.exposed_skills(events, contain.home, contain.world),
                   final=adapter.final_message(events), audit=audit)


def _text(value):
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def host_version(adapter, env):
    """The host's version string, or None when the host is missing."""
    try:
        done = subprocess.run(adapter.version_command(), capture_output=True, text=True, env=env, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None
