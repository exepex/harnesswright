"""Panel faults: a panel of graders that splits (doc 11, Harness faults), by the rule of `faults.py`: the plant is
made from its catalogue entry at a place a seed chooses, the panel (`grader.panel`) runs unchanged, and only the one
outcome it names counts as caught. It is planted on the goldens of one case of the repository, as the other grading
faults are (`grading_faults.py`), and covers every value of every choice the panel depends on.

- `tie`: two graders that answer one question (each in turn) or every question two ways, or one grader with no
  sheet, whose host's fresh grader stands in and answers half the questions the other way. A fresh tie-breaker must
  be asked exactly the split questions, and its answer, which sides with each grader on some question, must decide
  them; when the stand-in gives no sheet either, no question is answered and no tie-breaker is asked, so one grader
  never decides alone (`grader.panel`).

Standard library only.
"""

import grader
from grading_faults import _asked, _flip, _grader, _pages, _text


def _once(answer, calls):
    """A planted grader of a host whose first grader gives no sheet and whose next grader answers by `answer`, as
    `_grader` does."""
    def grade_one(page, asked):
        return _grader(answer if calls else None, calls)(page, asked)
    return grade_one


def tie(setup, fault, rng, place):
    """Two graders of one page that split as `place` says, and a fresh tie-breaker, by one rule for every place: on
    the split questions the tie-breaker sides with the first grader on some and with the second on the rest, each way
    in one of two panels. `one split` splits on each question in turn, `all split` on every question, and `one
    ungraded` on half the questions (at least one), where the second sheet comes from a fresh grader standing in for
    one that gave none, each grader being the ungraded one once for each side the tie-breaker takes. Caught when, in every panel, the tie-breaker is asked
    exactly the split questions and the panel takes its answers; with one grader ungraded, also when that host's
    grader is asked every question twice, and, when its stand-in gives no sheet either, nothing is answered and the
    tie-breaker is asked nothing: one grader never decides alone."""
    case, pages = _pages(setup, rng)
    golden, record, blob, asked = _asked(pages, rng)
    page, ids, settled = _text(case, record, blob), [question["id"] for question in asked], golden.settled
    splits = {"one split": [[id_] for id_ in ids], "all split": [ids],
              "one ungraded": [rng.sample(ids, max(1, len(ids) // 2))]}[place]
    orders = [rng.sample(split, len(split)) for split in splits]  # one order for both turns of a split
    swaps = (0, 1) if place == "one ungraded" else (0,)  # with one ungraded, each grader is the ungraded one once
    for (split, order), turn, swap in ((pair, turn, swap) for pair in zip(splits, orders) for turn in (0, 1)
                                       for swap in swaps):
        calls, again = [], []
        second = lambda id_, split=split: _flip(settled[id_]) if id_ in split else settled[id_]
        sides = {id_: (n + turn) % 2 for n, id_ in enumerate(order)}  # 0: with the first grader, 1: the second
        deciding = lambda id_, sides=sides: settled[id_] if sides.get(id_, 0) == 0 else _flip(settled[id_])
        pair = [_grader(settled.get), _once(second, again) if place == "one ungraded" else _grader(second)]
        found = grader.panel(page, asked, pair[::-1] if swap else pair, _grader(deciding, calls))
        want = {id_: deciding(id_) for id_ in ids}
        stood_in = place != "one ungraded" or again == [ids, ids]
        if calls != [[id_ for id_ in ids if id_ in split]] or found.answers != want or found.unanswered or not stood_in:
            return (f"one grader decided alone: the tie-breaker was asked {calls}, not the split {split}, the panel "
                    f"gave {found.answers}, and the ungraded host was asked {again}")
        if place == "one ungraded":  # its stand-in gives no sheet either
            calls, again = [], []
            pair = [_grader(settled.get), _once(None, again)]
            found = grader.panel(page, asked, pair[::-1] if swap else pair, _grader(deciding, calls))
            if calls or found.answers or again != [ids, ids]:
                return (f"one grader decided alone with no stand-in sheet: the tie-breaker was asked {calls}, the "
                        f"panel gave {found.answers}, and the ungraded host was asked {again}")
    return None


PLANTS = {"tie": (tie, ("one split", "all split", "one ungraded"), False)}
