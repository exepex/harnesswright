"""Text as the lint reads it: words after compatibility folding, and runs of consecutive words (doc 11, World lint).

A run of `RUN` words is the unit every text rule matches: shorter runs are ordinary project words.
"""

import re
import unicodedata

from cases import is_plain

RUN = 8


def words(text):
    """The words of `text` after compatibility folding, with format characters removed: lower-case runs of
    letters and digits in any script. `haiku-writer`, `Haiku_Writer` and `haiku writer` are the same words."""
    folded = "".join(c for c in unicodedata.normalize("NFKC", text) if unicodedata.category(c) != "Cf")
    # ASCII letters and digits form words of their own, so a name written flush against text in another script,
    # as in Chinese or Japanese prose, is still a word.
    return re.findall(r"[a-z0-9]+|[^\W_a-z0-9]+", folded.casefold())


def runs(text, sizes):
    """Every run of consecutive words of `text` whose length is one of `sizes`."""
    found = words(text)
    return {" ".join(found[i:i + n]) for n in sizes for i in range(len(found) - n + 1)}


def all_runs(texts, sizes):
    return set().union(set(), *(runs(t, sizes) for t in texts))


def plain(data):
    """`data` as text when it is UTF-8 and plain (`cases.is_plain`); otherwise None."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text if is_plain(text) else None
