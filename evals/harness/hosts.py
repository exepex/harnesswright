"""Load a host adapter from `adapters/<host>/adapter.py`, or from any adapter file (such as the test fake host)."""

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def load(host, path=None):
    """The adapter module for `host`. `path` names the adapter file directly."""
    path = Path(path) if path else REPO / "adapters" / host / "adapter.py"
    if not path.is_file():
        raise ValueError(f"no adapter for host {host!r} at {path}")
    spec = importlib.util.spec_from_file_location(f"adapter_{host.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
