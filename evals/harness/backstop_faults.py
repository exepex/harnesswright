"""Backstop faults: a without-skill run that copies a passage of the skill (doc 11, Baseline backstop), by the rule
of `faults.py`: planted from its catalogue entry at a place a seed chooses, its own gate runs unchanged, and only the
one outcome it names counts as caught.

The plant hands the host a passage of the skill's own text, at least `backstop.SPAN` words long, every run of it one
the skill protects, and asks for it word for word in a new world file or as the whole reply. The gate is
`backstop.check` on the run's stored bundle, the one function `runs.run` voids a without-skill run with. Caught when
it voids the run and the planted place alone holds a span that long: a void from the prompt's echo in the transcript
only, or from another text, is not this fault caught.

Standard library only.
"""

import backstop
import evidence
import skills
import world
from faults import Missed, _run

LONGEST = 40  # words of the passage: long enough to void, short enough for any host to copy whole
PLACES = {"world file": "into a new file named {file}", "message": "as your whole reply"}


def passage(setup, own, rng):
    """A passage of the skill's own text, `backstop.SPAN` to `LONGEST` words, whose every run `own` protects."""
    files, _ = skills.skill_files(setup.skill_dir, setup.case.skill)
    texts = [(path, data.decode("utf-8", "replace")) for path, data in sorted(files.items())]
    spans = [words.split() for _, length, words in backstop.matches(own, texts) if length >= backstop.SPAN]
    if not spans:
        raise Missed("the skill has no passage of its own long enough for the backstop, so none can be planted")
    said = rng.choice(spans)
    size = rng.randint(backstop.SPAN, min(len(said), LONGEST))
    start = rng.randrange(len(said) - size + 1)
    return " ".join(said[start:start + size])


def copied(setup, fault, rng, place):
    """A passage of the skill copied by a without-skill run, into a world file or its final message."""
    base = world.build(setup.case, setup.adapter, setup.folder() / "a", setup.skills_root)
    own = backstop.protected(setup.case, base, setup.skill_dir, setup.repo)
    planted = {"paragraph": passage(setup, own, rng), "file": f"notes-{rng.randrange(16 ** 6):06x}.md"}
    planted["where"] = PLACES[place].format(file=planted["file"])
    out, _ = _run(setup, fault, setup.case, planted)
    record, blob = evidence.load(out)
    found = backstop.check(record, blob, own)
    if not found["void"]:
        return f"the backstop did not void the run: its longest match was {_longest(found)} words"
    # The gate itself must void the planted place alone, every other text it reads left out, so a void found only
    # in another text (the prompt echoed in the transcript or the action log) is a miss.
    where = f"world/{planted['file']}" if place == "world file" else "final message"
    if not backstop.check(record, blob, own, where)["void"]:
        return f"the backstop voided the run, but not for the passage at {where}: {found['void'][0][0]}"
    return None


def _longest(found):
    return max((length for _, length, _ in found["void"] + found["short"]), default=0)


PLANTS = {"copied": (copied, tuple(PLACES), True)}
