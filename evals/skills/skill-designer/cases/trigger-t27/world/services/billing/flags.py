"""Feature flags for billing, read from flags.json."""

import json
from pathlib import Path

FLAGS = json.loads((Path(__file__).parent / "flags.json").read_text(encoding="utf-8"))


def enabled(key):
    return FLAGS.get(key, False)
