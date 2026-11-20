"""The one way out of a run (doc 11, Evidence): every value a bundle keeps passes one `Scrub`.

One rule: what a run made leaves only through `Scrub.text`, `Scrub.blob`, `Scrub.value` or `Scrub.names`, and each
looks at the whole raw value before anything cuts or encodes it. A canary token anywhere stops it with `Leak`: the
run is void and the round stops. Then every credential of the run (`credentials`) is redacted in every form
(`forms`). Transcript text also gets neutral words (`neutral=True`). A record is scrubbed before it is written as
JSON, so an escape can never hide a value. Its own field names are the harness's and are kept; keys the run chose,
such as paths, go through `names`, which refuses two that become one. What the harness made, such as a hash, is
never scrubbed.

Standard library only.
"""

import json
import string
from urllib.parse import quote, unquote, urlsplit

REDACTED = "[redacted]"
MIN_SECRET = 8  # the shortest credential a scrub can redact without damaging the evidence around it
# The characters a named credential may hold. Keys and tokens use only these, so a credential's every JSON form is
# itself and only URL encoding changes it: the scrub knows each form a run's output may hold.
SAFE = frozenset(string.ascii_letters + string.digits + "-_.~+/=")
NEUTRAL_NAME = "project-guide"  # the skill's name in a transcript
NEUTRAL_PATH = "guide-folder"  # each path the with-skill overlay installs, in a transcript
# The run's own folders, in a transcript, as their names on the machine may tell the arm or the round.
NEUTRAL_FOLDERS = {"world": "/run/project", "home": "/run/home", "scratch": "/run/scratch", "root": "/run"}


class Leak(RuntimeError):
    """A canary token reached a run's output. The run is void and the round stops."""


class UnsafeCredential(ValueError):
    """A credential the adapter names is too short, or holds a character outside SAFE, so it cannot be redacted
    reliably without damaging the evidence. The run cannot start."""


class Collision(RuntimeError):
    """Two keys of a record became one after scrubbing. The bundle cannot be written."""


def credentials(contained):
    """Every credential of the run `contained`, by one rule. A named credential is each value of the adapter's ENV_KEYS
    (from the operator and in the jail) and the secret part of a URL among them or of the operator's proxy: its
    password with its `user:password`, or its user when it has no password (a token), each as decoded. A named
    credential must be MIN_SECRET characters or more, all in SAFE; any other raises UnsafeCredential, since it could
    not be redacted reliably without damaging the evidence. A credential file's text and its
    JSON strings of at least MIN_SECRET characters are credentials too; a shorter string there is its metadata, such
    as a token type. Both the operator's file and the run's copy count."""
    named, pairs, unsafe = [], [], set()
    keys = getattr(contained.adapter, "ENV_KEYS", ())
    places = [(key, contained.operator_env.get(key, "")) for key in keys]
    places += [(key, getattr(contained, "env", {}).get(key, "")) for key in keys]
    for name, value in places + [("the operator's proxy", contained.upstream or "")]:
        secret, spellings = _userinfo(value) if "://" in value else (value, [])
        named += [secret] if secret else []
        pairs += spellings
        if secret and (len(secret) < MIN_SECRET or not set(secret) <= SAFE):
            unsafe.add(name)
    if unsafe:
        raise UnsafeCredential(f"the credential in {', '.join(sorted(unsafe))} cannot be redacted reliably: it must "
                               f"be at least {MIN_SECRET} characters of letters, digits and -_.~+/=")
    found = named + pairs
    for relative in getattr(contained.adapter, "CREDENTIAL_FILES", ()):
        for path in (contained.operator_home / relative, contained.home / relative):
            if path.is_file() and not path.is_symlink():
                text = path.read_text(errors="replace")
                found += [item for item in [text.strip(), *_strings(text)] if len(item) >= MIN_SECRET]
    return found


def _userinfo(url):
    """The secret part of a URL, decoded (its password, or its user when it has none), and its other spellings: its
    `user:password`, decoded and as the URL writes it, and the secret as the URL writes it."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url, []
    if parts.password:
        raw = parts.password
        written = [raw, f"{parts.username or ''}:{raw}", f"{unquote(parts.username or '')}:{unquote(raw)}"]
        return unquote(raw), written
    return (unquote(parts.username), [parts.username]) if parts.username else (None, [])


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
        found = {form for secret in secrets if isinstance(secret, str) and secret for form in forms(secret)}
        self.secrets = sorted(found, key=len, reverse=True)  # a longer secret first, so none is left half redacted
        self.neutral = sorted((neutral or {}).items(), key=lambda pair: len(pair[0]), reverse=True)

    @classmethod
    def of_run(cls, contained, overlay=None):
        """The scrub of the run `contained`, made after it ran so a credential the host refreshed is known, with
        neutral words for the run's folders and for the skill of `overlay` (`evidence.overlay`)."""
        import evidence  # here, as evidence imports this module: its one list of what the overlay covers
        neutral = folders(contained)
        if overlay:
            neutral.update({overlay["skill"]: NEUTRAL_NAME, **{p: NEUTRAL_PATH for p in evidence.places(overlay)}})
        return cls(contained.tokens, credentials(contained), neutral)

    def quiet(self, text):
        """`text` with every canary token and credential replaced, for a reason the harness reports, which may name
        a path the run chose."""
        for value in self.tokens + self.secrets:
            text = text.replace(value, REDACTED)
        return text

    def check(self, data, where):
        """Raise Leak when a canary token is anywhere in `data` (text or bytes)."""
        raw = data if isinstance(data, bytes) else data.encode(errors="surrogateescape")
        hit = next((token for token in self.tokens if token.encode() in raw), None)
        if hit:
            raise Leak(f"a canary token reached the run's output: {self.quiet(where)}")

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
        """A record (dicts, lists, strings and plain values) with every string value scrubbed. Its keys are the
        record's own fields, which the harness names, so they are checked for canaries and kept: a credential that
        happens to be part of a field's name never changes the record's shape. Keys the run chose go in `names`."""
        if isinstance(item, str):
            return self.text(item, where)
        if isinstance(item, list):
            return [self.value(part, where) for part in item]
        if isinstance(item, dict):
            for key in item:
                self.check(key, where)
            return {key: self.value(part, f"{where}/{key}") for key, part in item.items()}
        if item is None or isinstance(item, (bool, int, float)):
            return item
        raise TypeError(f"{where}: a record holds only dicts, lists, strings and plain values, not {type(item)}")

    def names(self, mapping, where="record"):
        """A map whose keys the run chose, such as paths, with its keys scrubbed; its values are the caller's. Two
        keys that become one are refused."""
        out = {}
        for key, part in mapping.items():
            name = self.text(key, where)
            if name in out:
                raise Collision(f"{where}: two keys are both {name!r} once scrubbed")
            out[name] = part
        return out


def folders(contained):
    """{the path of each of the run's folders: its neutral word}, as a folder's name may tell the arm or the round."""
    return {str(getattr(contained, name)): word for name, word in NEUTRAL_FOLDERS.items()
            if getattr(contained, name) is not None}


def forms(secret):
    """Every form of a credential a run's output may hold: as written, as a JSON string holds it, and decoded and
    encoded as a URL holds it (a URL's user and password are encoded, and a proxy decodes them)."""
    return {secret, json.dumps(secret)[1:-1], unquote(secret), quote(secret, safe="")} - {""}
