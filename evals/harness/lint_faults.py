"""Lint faults: a skill's name, its path or its own text, a test-tell word, the measuring kit's text or a whole eval
file, planted in a copy of the setup's case where a run would see it (doc 11, Harness faults), by the rule of
`faults.py`: each is planted from its catalogue entry at a place a seed chooses, the lint runs unchanged, and only
the refusal its plant names counts as caught.

Standard library only.
"""

import json
import shutil
from pathlib import Path

import cases
import faults
import lint
import world
from cases import REPO
from faults import Missed

NEUTRAL = "Keep it short."  # text that names, states and quotes nothing, so no rule of the lint refuses it


def _lint(setup, folder):
    """The lint's problems for the case in `folder`, as `lint.lint_skill` lints a skill's cases."""
    return lint.lint_skill(setup.case.skill, setup.adapter, folder.parent, setup.skills_root, setup.repo,
                           setup.skill_dir)


def _refused(setup, rng, where, plant, rule):
    """Plant at a place of kind `where` (`prompt`, `file` or `existing`) and check that the lint refuses that place
    by `rule`, the words of the one problem the plant must cause. `plant(folder, data, place, text)` puts `text` at
    `place` and returns its key (a world path or `<prompt>`), with `text` None for the plant itself.

    One rule chooses the place: the plant goes only where its rule is the one that decides. That is a place where the
    same plant with neutral text in its stead leaves the lint clean, so whatever the lint says there after the plant,
    the planted text caused it. Of the places of kind `where`, in the order the seed gives, the plant takes the first
    such place. Another problem at that place is never this fault caught."""
    folder, _ = faults._copy(setup)
    control = _lint(setup, folder)
    if control:
        return f"the clean case does not pass the lint, so the fault proves nothing: {control[0]}"
    for place in _places(folder, where, rng):
        folder, data = faults._copy(setup)
        plant(folder, data, place, NEUTRAL)
        (folder / "case.json").write_text(json.dumps(data))
        if _lint(setup, folder):
            continue  # another rule decides here, so a refusal here would prove nothing of this one
        folder, data = faults._copy(setup)
        key = plant(folder, data, place, None)
        (folder / "case.json").write_text(json.dumps(data))
        found = _lint(setup, folder)
        if any(problem.startswith(f"{setup.case.id}: {key}: ") and rule in problem for problem in found):
            return None
        return f"the lint did not refuse {key} as {rule!r}: {found[:2]}"
    raise Missed(f"no {where} place where {rule!r} alone decides: the lint refuses neutral text at each one")


def _places(folder, where, rng):
    """The places of kind `where` in the case copy at `folder`, in the order the seed gives: the prompt, a new world
    file, or each existing world file the lint reads as text (a new file when the world has none)."""
    if where == "prompt":
        return [cases.PROMPT_KEY]
    files = sorted(str(p.relative_to(folder / "world")) for p in (folder / "world").rglob("*")
                   if p.is_file() and not p.is_symlink() and lint.plain(p.read_bytes()) is not None)
    if where == "existing" and files:
        rng.shuffle(files)
        return files
    return [f"notes-{rng.randrange(16 ** 6):06x}.md"]


def _put(folder, data, place, text):
    """Put `text` at `place`: the end of the prompt, the end of an existing world file, or a new world file."""
    if place == cases.PROMPT_KEY:
        data["prompt"] += f" {text}"
        return place
    path = folder / "world" / place
    if path.is_file():
        path.write_text(path.read_text() + f"\n{text}\n")
    else:
        path.write_text(f"# Notes\n\n{text}\n")
    return place


def names(setup, fault, rng, place):
    """The skill's name, its path, or a run of its own text (its fingerprint) at a place the run sees. Caught when
    the lint refuses that place."""
    where, what = place.split("/")
    skill = setup.case.skill
    if what == "name":
        text = f"Ask {skill} for help here."
    elif what == "path":
        text = f"See {setup.case.skill_rel} first."
    else:
        # A run of the skill's own text that the lint protects in this case, as the lint itself finds them.
        repo, arm = Path(setup.repo), world.build(setup.case, setup.adapter, setup.folder() / "a", setup.skills_root)
        copied, _ = lint.verified_copies(setup.case, repo)
        own = sorted(lint.protected(setup.case, lint.visible(setup.case, arm), copied, setup.skill_dir,
                                    lint.texts(repo / "evals" / "skills" / skill / "upstream"), repo)[1])
        if not own:
            raise Missed("the skill has no text of its own for the lint to protect, so no fingerprint can be planted")
        text = rng.choice(own)
    rule = "of the skill's own text" if what == "fingerprint" else "names the skill"
    return _refused(setup, rng, where, lambda folder, data, place, neutral: _put(folder, data, place, neutral or text),
                    rule)


def tells(setup, fault, rng, place):
    """A test-tell word, a run of the measuring kit's own text, or a whole eval file (a copy of this catalogue) at a
    place the run sees. Caught when the lint refuses that place."""
    where, what = place.split("/")
    if what == "eval file":
        name = f"plan-{rng.randrange(16 ** 6):06x}.json"

        def plant(folder, data, place, neutral):  # the catalogue's copy, or a file of the same name that says nothing
            if neutral:
                (folder / "world" / name).write_text(json.dumps({"note": neutral}) + "\n")
            else:
                shutil.copyfile(Path(setup.repo) / faults.CATALOGUE.relative_to(REPO), folder / "world" / name)
            return name
        return _refused(setup, rng, where, plant, "holds eval text")
    if what == "word":
        allowed = {" ".join(lint.words(w)) for ws in setup.case.allow_words.values() for w in ws}  # a case's own
        text = f"Keep the {rng.choice([t for t in lint.TELLS if t not in allowed])} notes short."
    else:
        rows = [w for e in faults.load(Path(setup.repo) / faults.CATALOGUE.relative_to(REPO))
                for w in [e.get("prompt", "").split()] if len(w) >= lint.RUN]
        said = rng.choice(rows)
        start = rng.randrange(len(said) - lint.RUN + 1)
        text = " ".join(said[start:start + lint.RUN])
    rule = "test-tell word" if what == "word" else "holds eval text"
    return _refused(setup, rng, where, lambda folder, data, place, neutral: _put(folder, data, place, neutral or text),
                    rule)


SPOTS = ("file", "existing", "prompt")
# Each plant: its function, its places, and whether it runs a case on a host (so needs a prompt, and stores a bundle).
PLANTS = {
    "names": (names, tuple(f"{s}/{w}" for s in SPOTS for w in ("name", "path", "fingerprint")), False),
    "tells": (tells, tuple(f"{s}/{w}" for s in SPOTS for w in ("word", "kit text")) + ("file/eval file",), False),
}
