"""The cross-model comparison report (doc 11, Cross-model grading): what one finished regrade pass found, per grader
route and per pair of routes. A measurement, not a gate: it gives no label and changes nothing of the round.

One rule: a route's answer to a question on a page is the one answer every grader of that route gave it. When its
graders gave two answers the question is `split` for that route, and when any of them gave no answer (no accepted
sheet) it is `ungraded`; both are counted apart and never read as yes or no. Every figure carries its counts.

- Per route: golden accuracy (right of asked, split and ungraded named); the share of questions its graders agree
  on, when it had two a page; the questions a golden miss leaves untrusted for it, by the golden gate's own rule
  (`goldens.gate`); every sheet it could not give, with each try's reason; seconds, tokens and money by the price
  file the pass names; its adapter hash, host version, pinned upstream and the probes and faults it passed.
- Per pair of routes: agreement on the questions both answered, as counts and Cohen's kappa, each kind of page
  apart, and every disagreement with its page, case, question and both answers. Run pages made by a host of a
  route's own family (`family`, named by the operator) are reported apart for that pair, with the same figures.
- Per pass: what it graded, and the limits of the plan that hold for every report (`LIMITS`).

It reads only the pass folder, `<store>/<round>/regrade/<pass>/`, and refuses a pass with no finish time, which
stopped part way. It writes `report.json` there. All it holds comes from the pass's own files, each of which passed
the scrub of the containments the pass made.

    python3 evals/harness/compare.py PASS_FOLDER [--family HOST ADAPTER=MODEL ...]

Standard library only.
"""

import argparse
import itertools
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True  # its imports leave no bytecode in the kit's folder, which must hold only tracked files

import goldens  # noqa: E402
import grading  # noqa: E402
import prices  # noqa: E402
import regrade  # noqa: E402
import rounds  # noqa: E402
from cases import REPO  # noqa: E402
from host import TOKENS  # noqa: E402
from measures import share  # noqa: E402

SPLIT, UNGRADED = "split", "ungraded"
ONE = "Each route gave one grader a page: every answer is one grader's, nothing can split, and no agreement of a " \
      "route's own graders is measured."
LIMITS = (  # every limit of the plan that still holds, stated in every report so no figure is read for more
    "Only the goldens are ground truth. Golden accuracy leans toward the model families that settled and tuned the "
    "questions; agreement with the round's panel is concordance, not accuracy.",
    "Host and model are mixed: a model in one host is not the same as that model in its own host. A route to a "
    "family the round's hosts already have shows the host's own effect.",
    "No judge approves an adapter by hash: the round's manifest pins its hosts' adapters, and the pass records each "
    "route's adapter hash and host version.",
    "A route that names no upstream is not pinned to one, and hosts do not report the upstream that served a try.",
    "The samples are small, one pass of the pages each case has: read every figure with its counts.",
    "Runs of a route's own model family are reported apart only where the operator named that family.")


class CompareError(rounds.RoundError):
    """The pass cannot be reported, and why."""


def answer(graders, id_):
    """A route's answer to question `id_` from the records of its graders of one page (see the module's rule)."""
    given = [None if g["sheet"] is None else {a["id"]: a["answer"] for a in g["sheet"]["answers"]}.get(id_)
             for g in graders]
    if None in given:
        return UNGRADED
    return given[0] if len(set(given)) == 1 else SPLIT


def kappa(pairs):
    """Cohen's kappa of two raters' yes or no answers, [(a, b)], or None when it is not defined."""
    n = len(pairs)
    if not n:
        return None
    seen = sum(a == b for a, b in pairs) / n
    chance = sum((sum(a == x for a, _ in pairs) / n) * (sum(b == x for _, b in pairs) / n) for x in grading.ANSWERS)
    return None if chance == 1 else round((seen - chance) / (1 - chance), 4)


class _Fields(dict):
    """An object of one file of the pass: a field it lacks names the file."""

    def __init__(self, fields, path):
        super().__init__(fields)
        self.path = path

    def __missing__(self, key):
        raise CompareError(f"{self.path}: no field {key!r}")


def _load(path):
    """The JSON of `path`, the one reader of the pass's files: every object in it names `path` when a field is
    missing."""
    return json.loads(path.read_text(), object_hook=lambda fields: _Fields(fields, path))


def read(out):
    """(head, pages, {route key: (route entry, {place: graders}, its proof)}) of the finished pass in `out`."""
    out = Path(out)
    head = _load(out / "regrade.json")
    if not head.get("finished"):
        raise CompareError(f"{out}: the pass has no finish time, so it stopped part way")
    pages = _load(out / "pages.json")
    routes = {}
    for entry in head["routes"]:
        folder = out / entry["folder"] / "pages"
        graded = {path.stem: _load(path)["graders"] for path in sorted(folder.glob("*.json"))}
        if set(graded) != set(pages):
            raise CompareError(f"route {entry['adapter']}={entry['model']}: it did not grade every page of the pass")
        proved = _load(out / entry["folder"] / "proved.json")
        routes[f"{entry['adapter']}={entry['model']}"] = (entry, graded, proved)
    return head, pages, routes


def report(out, family=None, repo=REPO):
    """The report of the pass in folder `out`. `family` is {route key: [hosts of that route's model family]}."""
    head, pages, routes = read(out)
    family = family or {}
    unknown = sorted(set(family) - set(routes))
    if unknown:
        raise CompareError(f"--family names routes the pass did not run: {', '.join(unknown)}")
    price_file = prices.load(repo)
    if price_file["date"] != head["prices"]:
        raise CompareError(f"the price file is dated {price_file['date']}, the pass {head['prices']}")
    answers = {key: {place: {id_: answer(graded[place], id_) for id_ in page["asked"]}
                     for place, page in pages.items()} for key, (_, graded, _) in routes.items()}
    found = {"limits": list(LIMITS),
             "pass": {**{k: head[k] for k in ("round", "source", "commit", "kit", "seed", "pages", "graders", "prices",
                                              "prompt")},
                      "pages graded": {kind: sum(p["kind"] == kind for p in pages.values()) for kind in head["pages"]},
                      "family": {key: sorted(hosts) for key, hosts in sorted(family.items())},
                      **({"one grader": ONE} if head["graders"] == 1 else {})},
             "routes": {key: _route(entry, graded, proved, pages, answers[key], head["graders"], price_file)
                        for key, (entry, graded, proved) in routes.items()},
             "pairs": [_pair(a, b, pages, answers, family) for a, b in itertools.combinations(sorted(routes), 2)]}
    return found


def _route(entry, graded, proved, pages, answers, graders, price_file):
    right = asked = splits = ungraded = 0
    agree = both = 0
    by_case = {}
    for place, page in pages.items():
        for id_ in page["asked"]:
            given = answers[place][id_]
            if page["kind"] == "golden":
                asked += 1
                right += given == page["settled"][id_]
                splits += given == SPLIT
                ungraded += given == UNGRADED
            if graders > 1 and given != UNGRADED:
                both += 1
                agree += given != SPLIT
        if page["kind"] == "golden":
            by_case.setdefault(page["case"], {})[page["name"]] = (page, answers[place])
    untrusted = {}
    for case, found in sorted(by_case.items()):
        size = len(next(iter(found.values()))[0]["settled"])
        made = [SimpleNamespace(name=name, settled=page["settled"]) for name, (page, _) in found.items()]
        gate = goldens.gate(SimpleNamespace(expectations=[None] * size), made, {
            name: (page["asked"], {i: a for i, a in given.items() if a in grading.ANSWERS}, [])
            for name, (page, given) in found.items()})
        asked_ids = {id_ for page in pages.values() if page["case"] == case for id_ in page["asked"]}  # runs too
        untrusted.update({f"{case}/{id_}": why for id_, why in gate.items() if why and id_ in asked_ids})
    refused = [{"page": place, "grader": number, "tries": g["tries"]} for place, gs in sorted(graded.items())
               for number, g in enumerate(gs, start=1) if g["sheet"] is None]
    return {**{k: entry.get(k) for k in ("adapter", "model", "version", "upstream", "adapter_sha256")},
            "proved": {"not run": proved["not run"], "faults": proved["faults"]},
            "golden accuracy": share(right, asked, right=right, asked=asked, split=splits, ungraded=ungraded),
            "graders agree": share(agree, both, agreed=agree, answered=both) if graders > 1 else None,
            "untrusted": untrusted, "refused": refused, "cost": _cost(graded, price_file)}


def _cost(graded, price_file):
    cost = {"tries": 0, "seconds": 0, "untimed": 0, "uncounted": 0, "unpriced": 0, "money": 0, "tokens": {}}
    for costs in (one for gs in graded.values() for g in gs for one in g["costs"]):
        cost["tries"] += 1
        if isinstance(costs.get("seconds"), (int, float)):
            cost["seconds"] = round(cost["seconds"] + costs["seconds"], 3)
        else:
            cost["untimed"] += 1
        if not costs.get("tokens"):
            cost["uncounted"] += 1
            continue
        for model, counts in costs["tokens"].items():
            total = cost["tokens"].setdefault(model, dict.fromkeys(TOKENS, 0))
            for name in TOKENS:
                total[name] += counts[name]
        money = prices.cost(costs["tokens"], price_file)
        cost["unpriced"] += money is None
        cost["money"] += money or 0
    cost["money"] = round(cost["money"], 6)  # of the priced tries only: `unpriced` and `uncounted` name the rest
    return cost


def _pair(a, b, pages, answers, family):
    """Two routes' agreement on the questions both answered yes or no, and every disagreement: the runs of either
    route's own model family apart from the rest, each kind of page apart."""
    groups = {"others": {}, "own family": {}}
    for place, page in sorted(pages.items()):
        own = page["kind"] == "run" and page["host"] in family.get(a, []) + family.get(b, [])
        group = groups["own family" if own else "others"]
        for id_ in page["asked"]:
            one, other = answers[a][place][id_], answers[b][place][id_]
            if one in grading.ANSWERS and other in grading.ANSWERS:
                group.setdefault(page["kind"], []).append((one, other, place, page, id_))
    return {"routes": [a, b], **{name: {
        "agreement": {kind: {**share(sum(x == y for x, y, *_ in found), len(found),
                                     agreed=sum(x == y for x, y, *_ in found), answered=len(found)),
                             "kappa": kappa([(x, y) for x, y, *_ in found])} for kind, found in sorted(kinds.items())},
        "disagreements": [{"page": place, "name": page["name"], "case": page["case"], "question": id_, a: x, b: y,
                           **({"settled": page["settled"][id_]} if page["settled"] else {})}
                          for found in kinds.values() for x, y, place, page, id_ in found if x != y]}
        for name, kinds in groups.items()}}


def main(argv=None, repo=REPO):
    parser = argparse.ArgumentParser(prog="compare.py", description="Report one cross-model grading pass.")
    parser.add_argument("folder", help="the pass folder, <store>/<round>/regrade/<pass>")
    parser.add_argument("--family", nargs=2, action="append", default=[], metavar=("HOST", "ADAPTER=MODEL"),
                        help="a host whose runs that route's model family made (repeatable)")
    args = parser.parse_args(argv)
    try:
        family = {}
        for host, key in args.family:
            family.setdefault("=".join(regrade.route(key)), []).append(host)
        found = report(args.folder, family, repo)
        fresh = Path(args.folder) / ".report.json"  # whole, as the store's files are written: beside it, then moved
        fresh.write_text(json.dumps(found, indent=1, sort_keys=True) + "\n")
        os.replace(fresh, fresh.with_name("report.json"))
    except (rounds.RoundError, prices.PriceError, OSError, ValueError, KeyError) as error:  # a pass it cannot read
        print(f"compare: {error}", file=sys.stderr)
        return 1
    for key, route in found["routes"].items():
        accuracy = route["golden accuracy"]
        print(f"{key}: golden accuracy {accuracy['right']}/{accuracy['asked']}, untrusted {len(route['untrusted'])}, "
              f"refused {len(route['refused'])}, ${route['cost']['money']} (tries not priced: "
              f"{route['cost']['unpriced'] + route['cost']['uncounted']})")
    for pair in found["pairs"]:
        for name in ("others", "own family"):
            print(f"{' vs '.join(pair['routes'])}, {name}: {len(pair[name]['disagreements'])} disagreements"
                  + "".join(f", {kind} kappa {a['kappa']}" for kind, a in pair[name]["agreement"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
