"""What a case's expectations cite (doc 11, World lint): the contract quote of each expectation, held where it is
cited, the checks it names, and the rule that a task case of a skill with a kind has at least one contract
expectation, so that its runs are scored. Split out of lint.py by purpose; `lint.lint` reads it.

Standard library only.
"""

import json

import cases
import checks
from cases import kinds
from textruns import words

SHORTEST = 3  # words a quote or an expectation text needs before it is told apart from ordinary project words


def citations(case, places):
    """(quotes, problems): for each expectation, the quote of its contract when a world text file holds it where it
    is cited, else None; and a problem for each quote not held there, and for each check whose name or arguments
    are not in the check library. A quote starts on its line, in the words the lint reads, and may run on over the
    lines after it. A task case of a skill with a kind (`cases.kinds`) and no contract expectation is a problem
    too: none of its runs would be scored. A skill with no kind gets no label, so its cases need none. An internal
    task case also needs a contract expectation that one of harnesswright's own checks decides
    (`verdicts.own_checked`), or the round lists it unchecked."""
    found, problems, library = [], [], None
    documents = {p.key: p.text.split("\n", 1)[1] for p in places
                 if p.kind in ("world", "base", "derived") and p.text is not None and not p.link}
    for number, expectation in enumerate(case.expectations, 1):
        if "check" in expectation:
            try:
                library = checks.library() if library is None else library
                checks.validate(expectation["check"]["name"], expectation["check"]["args"], library)
            except checks.CheckError as error:
                problems.append(f"expectation {number}: {error}")
        source = expectation["source"]
        found.append(None)
        if source in ("format", "done"):
            continue
        path, line, quote = source["contract"]["path"], source["contract"]["line"], source["contract"]["quote"]
        rows = documents[path].splitlines() if path in documents else []
        here = " ".join(words(rows[line - 1])) if line <= len(rows) else ""
        rest, said = " ".join(words("\n".join(rows[line - 1:]))), " ".join(words(quote))
        at = f" {rest} ".find(f" {said} ")  # where the quote's first word starts in `rest`, or -1
        if len(said.split()) < SHORTEST or not here or not 0 <= at < len(here):
            problems.append(f"expectation {number}: {path}:{line} does not start the quote {quote[:80]!r}, of at "
                            f"least {SHORTEST} words" + ("" if path in documents else f"; no world text file {path}"))
            continue
        found[-1] = quote
    scored = case.data["kind"] == "task" and kinds().get(case.skill)  # only a skill with a kind gets a label
    if scored and not any(isinstance(e["source"], dict) for e in case.expectations):
        problems.append("a task case needs at least one contract expectation: with none, no run of it is scored "
                        "(verdicts.task_outcome), and its skill's label stays at most inconclusive")
    import verdicts  # here, not at the top: verdicts reaches lint, which imports this module
    own = cases.own_checks() if scored == "internal" else []
    if scored == "internal" and not any(verdicts.own_checked(e, own) for e in case.expectations):
        problems.append("an internal task case needs a contract expectation that one of harnesswright's own checks "
                        "decides (evals/own-checks.json): with none, the round lists it unchecked and its skill's "
                        "label stays at most inconclusive (verdicts.decide)")
    return found, problems


def expectation_texts(expectation):
    """Every text an expectation holds: what it says, and its judged question, rules and examples."""
    judged = expectation.get("judged") or {}
    examples = judged.get("examples", {})
    return [expectation["text"]] + [judged[k] for k in ("question", "pass", "fail") if k in judged] \
        + examples.get("pass", []) + examples.get("fail", [])


def stated_quotes(text):
    """The contract quotes a case data file states, or none when it is not a case.json of that shape."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    found = data.get("expectations") if isinstance(data, dict) else None
    if not isinstance(found, list):
        return []
    return [e["source"]["contract"]["quote"] for e in found if isinstance(e, dict) and isinstance(e.get("source"), dict)
            and isinstance(e["source"].get("contract"), dict) and isinstance(e["source"]["contract"].get("quote"), str)]
