"""What a run cost: its token counts by model (`host.TOKENS`, as the bundle keeps them) priced by one dated price
file, `evals/results/prices.json`.

The price file names its date, its sources and, per model, a price in US dollars per million tokens for each of
`host.TOKENS`. Its "input" price is for input neither read from nor written to the cache, since a host's "input"
count holds all input: a run's input at that price is its input less its cache reads and cache writes. Its notes
say what the file could not price exactly, such as a cache write priced at one lifetime. `load` reads the file and
refuses any other field or shape. `cost` gives the money of one run, or None when the run has no counts or a model
of the run has no price: money is never estimated. Model names live here only because `evals/results/` is the one
place AGENTS.md allows them.

Standard library only.
"""

import json
import re
from fractions import Fraction

from host import TOKENS

PATH = ("evals", "results", "prices.json")  # under the repository
FIELDS = {"date", "currency", "per", "sources", "notes", "models"}


class PriceError(Exception):
    """The price file, or the counts it prices, is not as this module allows."""


def _text(value, most=500):
    return isinstance(value, str) and 0 < len(value) <= most and value.isprintable()


def _price(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < 10_000


def check(data):
    """Raise PriceError unless `data` is a price file: its date (YYYY-MM-DD), "USD", 1000000 tokens per price, one
    or more https sources, its notes, and one or more models each with a price for each of TOKENS and nothing
    else."""
    problems = []
    if not isinstance(data, dict) or set(data) != FIELDS:
        raise PriceError(f"a price file has exactly the fields {sorted(FIELDS)}")
    if not (isinstance(data["date"], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["date"])):
        problems.append("date is not YYYY-MM-DD")
    if data["currency"] != "USD" or data["per"] != 1_000_000 or isinstance(data["per"], bool):
        problems.append('prices are in "USD" per 1000000 tokens')
    if not (isinstance(data["sources"], list) and data["sources"] and all(
            _text(source) and source.startswith("https://") for source in data["sources"])):
        problems.append("sources are one or more https links")
    if not (isinstance(data["notes"], list) and all(_text(note, 1000) for note in data["notes"])):
        problems.append("notes are a list of texts")
    models = data["models"]
    if not (isinstance(models, dict) and models and all(
            _text(name, 200) and isinstance(price, dict) and sorted(price) == sorted(TOKENS)
            and all(_price(value) for value in price.values()) for name, price in models.items())):
        problems.append(f"models map each model to a price for each of {list(TOKENS)}")
    if problems:
        raise PriceError("; ".join(problems))
    return data


def load(repo):
    """The price file of the repository `repo`, checked."""
    path = repo.joinpath(*PATH)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PriceError(f"{path}: {error}") from None
    return check(data)


def cost(tokens, prices):
    """The money, in dollars rounded to a millionth, of a run whose counts are `tokens` ({model: {name: count}}, or
    None), at the checked price file `prices`; None when there are no counts or a model has no price. Counts whose
    cache reads and writes exceed their input raise PriceError, as no host reports that."""
    if tokens is None or not set(tokens) <= set(prices["models"]):
        return None
    total = Fraction(0)
    for model, counts in tokens.items():
        price = {name: Fraction(str(value)) for name, value in prices["models"][model].items()}
        plain = counts["input"] - counts["cache read"] - counts["cache write"]
        if plain < 0:
            raise PriceError(f"{model}: cache reads and writes exceed all input")
        total += (plain * price["input"] + counts["cache read"] * price["cache read"]
                  + counts["cache write"] * price["cache write"] + counts["output"] * price["output"])
    return float(round(total / prices["per"], 6))
