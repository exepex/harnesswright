"""The one way out of a run (doc 11, Evidence): every value a bundle keeps passes one `Scrub`.

One rule: a value leaves a run only through `Scrub.text`, `Scrub.blob` or `Scrub.value`, and each looks at the
whole raw value before anything cuts or encodes it. A canary token anywhere stops it with `Leak`: the run is void
and the round stops. Then every credential value of the run is redacted. Transcript text also has the skill's name
and paths replaced by neutral words (`neutral=True`). A record is scrubbed before it is written as JSON, so an
escape can never hide a value, and its keys are scrubbed too, so a name that differs from another only by a secret
is refused rather than merged.

Standard library only.
"""

import json
import re
from urllib.parse import urlsplit

REDACTED = "[redacted]"
MIN_SECRET = 8  # a shorter value is not a credential, and redacting it would garble the evidence
NEUTRAL_NAME = "project-guide"  # the skill's name in a transcript
NEUTRAL_PATH = "guide-folder"  # each path the with-skill overlay installs, in a transcript


class Leak(RuntimeError):
    """A canary token reached a run's output. The run is void and the round stops."""


class Collision(RuntimeError):
    """Two keys of a record became one after scrubbing. The bundle cannot be written."""


def credentials(contained):
    """Every credential value of the run `contained`: each value its adapter's ENV_KEYS take from the operator (for a
    URL, only its user and password), the user and password of the operator's proxy, and the text and every JSON
    string value of each credential file, both the operator's and the run's copy, which the host may have refreshed."""
    found = []
    for key in getattr(contained.adapter, "ENV_KEYS", ()):
        value = contained.operator_env.get(key, "")
        found += _userinfo(value) if "://" in value else [value]
    found += _userinfo(contained.upstream or "")
    for relative in getattr(contained.adapter, "CREDENTIAL_FILES", ()):
        for path in (contained.operator_home / relative, contained.home / relative):
            if path.is_file() and not path.is_symlink():
                text = path.read_text(errors="replace")
                found += [text.strip(), *_strings(text)]
    return found


def _userinfo(url):
    try:
        parts = urlsplit(url)
    except ValueError:
        return [url]
    return [part for part in (parts.username, parts.password) if part]


def _strings(text):
    try:
        data = json.loads(text)
    except ValueError:
        return []
    found, stack = [], [data]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            stack += item.values()
        elif isinstance(item, list):
            stack += item
        elif isinstance(item, str):
            found.append(item)
    return found


class Scrub:
    """The scrub of one run: its canary `tokens`, its credential `secrets` and its `neutral` words, a map of the
    skill's name and paths to the words a transcript shows instead."""

    def __init__(self, tokens, secrets, neutral=None):
        self.tokens = sorted(set(tokens))
        forms = set()
        for secret in secrets:
            if isinstance(secret, str) and len(secret) >= MIN_SECRET:
                forms |= {secret, json.dumps(secret)[1:-1]}  # as written, and as a JSON string holds it
        self.secrets = sorted(forms, key=len, reverse=True)  # a longer secret first, so none is left half redacted
        self.neutral = sorted((neutral or {}).items(), key=lambda pair: len(pair[0]), reverse=True)

    @classmethod
    def of_run(cls, contained, overlay=None):
        """The scrub of the run `contained`, with neutral words for the skill of `overlay` (`evidence.overlay`)."""
        neutral = {}
        if overlay:
            neutral = {overlay["skill"]: NEUTRAL_NAME, **{path: NEUTRAL_PATH for path in overlay["paths"]}}
        return cls(contained.tokens, credentials(contained), neutral)

    def check(self, data, where):
        """Raise Leak when a canary token is anywhere in `data` (text or bytes)."""
        raw = data if isinstance(data, bytes) else data.encode(errors="surrogateescape")
        hit = next((token for token in self.tokens if token.encode() in raw), None)
        if hit:
            raise Leak(f"a canary token reached the run's output: {where}")

    def text(self, value, where="text", neutral=False):
        """`value` as a bundle may keep it: checked for canaries, then redacted, then (for a transcript) neutral."""
        self.check(value, where)
        for secret in self.secrets:
            value = value.replace(secret, REDACTED)
        if neutral:
            for word, instead in self.neutral:
                value = value.replace(word, instead)
        return value

    def blob(self, data, where="file"):
        """The bytes of a file as a bundle may keep them: checked for canaries, then redacted."""
        self.check(data, where)
        for secret in self.secrets:
            data = data.replace(secret.encode(), REDACTED.encode())
        return data

    def value(self, item, where="record"):
        """A record (dicts, lists, strings and plain values) with every string scrubbed, keys included."""
        if isinstance(item, str):
            return self.text(item, where)
        if isinstance(item, list):
            return [self.value(part, where) for part in item]
        if isinstance(item, dict):
            out = {}
            for key, part in item.items():
                name = self.text(key, where) if isinstance(key, str) else key
                if name in out:
                    raise Collision(f"{where}: two keys are both {name!r} once scrubbed")
                out[name] = self.value(part, f"{where}/{name}")
            return out
        if item is None or isinstance(item, (bool, int, float)):
            return item
        raise TypeError(f"{where}: a record holds only dicts, lists, strings and plain values, not {type(item)}")
