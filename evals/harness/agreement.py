"""Grader agreement per question (doc 12, Grader agreement): how often the graders of a round agree on each judged
question, read from the round's grade records.

One rule: a judged question, an expectation of one case (`<skill>/<case> q<n>`), is counted over every page of the
round that asked it, the runs, extra runs included, and the goldens alike, and over every answer a grader gave it:
each grader's accepted sheet, the sheets it gave in tries refused for their form (`offered`, `grader.given`) and the
tie-breaker's. A page agrees on the question when every answer given to it there is the same; a page with fewer
than two answers says nothing about agreement and is left out. A question below `AGREEMENT`, or one a grader's
retry flipped on some page (`flipped`, `grader.flipped`), is named for rewriting (`rewrite`). Agreement unscores
nothing: a run is unscored on a question only where that page's own answer is not settled (`grader.panel`).

Standard library only.
"""

import json

import measures

AGREEMENT = 0.9  # a judged question below it is named for rewriting (doc 12, Grader agreement)


def questions(folder, attempt, graded_runs):
    """{"questions": {question: {"agreement", "flipped"}}, "rewrite": [question]} of attempt `attempt` of the round
    in `folder` (`<store>/<round>`): every run of `graded_runs` (the grade outcome's runs, extra runs included,
    `labels.with_extras`) and every golden its gradings graded."""
    grades = folder / "grades" / attempt
    pages = [(made["key"], json.loads((grades / "runs" / f"{made['key']}.json").read_text()), None)
             for made in graded_runs]
    for path in sorted([*grades.glob("goldens/*/*/*.json"), *grades.glob("extra-*/goldens/*/*/*.json")]):
        case = f"{path.parent.parent.name}/{path.parent.name}"
        pages.append((f"golden {case}/{path.stem} ({path.relative_to(grades).parts[0]})", json.loads(path.read_text()),
                      case))
    found = {}
    for name, record, case in pages:
        given = {}  # each question's answers on this page, from every try of every grader
        for grader in record.get("graders", []):
            for answers in [*(grader.get("offered") or []), _accepted(grader.get("sheet"))]:
                for id_, answer in (answers or {}).items():
                    given.setdefault(id_, []).append(answer)
        for id_ in record["asked"]:
            here = found.setdefault(f"{case or record['case']} {id_}", {"agreed": 0, "pages": 0, "flipped": []})
            if len(given.get(id_, [])) >= 2:
                here["pages"] += 1
                here["agreed"] += len(set(given[id_])) == 1
            if id_ in record.get("flipped", []):
                here["flipped"].append(name)
    report = {question: {"agreement": measures.share(tally["agreed"], tally["pages"], agreed=tally["agreed"],
                                                     pages=tally["pages"]), "flipped": tally["flipped"]}
              for question, tally in sorted(found.items())}
    return {"questions": report, "rewrite": [
        question for question, tally in report.items()
        if tally["flipped"] or tally["agreement"]["rate"] is not None and tally["agreement"]["rate"] < AGREEMENT]}


def _accepted(sheet):
    return {answer["id"]: answer["answer"] for answer in sheet["answers"]} if sheet else None
