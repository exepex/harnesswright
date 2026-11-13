"""Money: a run's token counts by model, priced by one dated price file, and never estimated."""

import copy
import json
import unittest
from pathlib import Path

from helpers import TempCase

import prices

REPO = Path(__file__).resolve().parents[3]
PRICES = {"date": "2026-11-12", "currency": "USD", "per": 1_000_000, "sources": ["https://example.com/prices"],
          "notes": ["one rate for a cache write"],
          "models": {"model-a": {"input": 2, "cache read": 0.1, "cache write": 2.5, "output": 10},
                     "model-b": {"input": 1, "cache read": 0.05, "cache write": 1.25, "output": 5}}}


def counts(input_, read=0, write=0, output=0):
    return {"input": input_, "cache read": read, "cache write": write, "output": output}


class Load(TempCase):
    def test_the_repositorys_price_file_is_one_this_module_allows(self):
        data = prices.load(REPO)
        self.assertRegex(data["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertTrue(data["models"])

    def test_a_price_file_of_any_other_field_or_shape_is_refused(self):
        def broken(change):
            data = copy.deepcopy(PRICES)
            change(data)
            return data

        for data in (broken(lambda d: d.update(extra=1)), broken(lambda d: d.pop("notes")),
                     broken(lambda d: d.update(date="12 Nov 2026")), broken(lambda d: d.update(currency="EUR")),
                     broken(lambda d: d.update(per=1000)), broken(lambda d: d.update(sources=[])),
                     broken(lambda d: d.update(sources=["http://example.com"])),
                     broken(lambda d: d.update(models={})),
                     broken(lambda d: d["models"]["model-a"].pop("cache write")),
                     broken(lambda d: d["models"]["model-a"].update(output=-1)),
                     broken(lambda d: d["models"]["model-a"].update(output=True)),
                     broken(lambda d: d["models"]["model-a"].update(output="10")), [PRICES]):
            with self.subTest(data=data), self.assertRaises(prices.PriceError):
                prices.check(data)
        self.assertIs(prices.check(PRICES), PRICES)
        (self.tmp / "evals" / "results").mkdir(parents=True)
        (self.tmp / "evals" / "results" / "prices.json").write_text("{not json")
        with self.assertRaisesRegex(prices.PriceError, "prices.json"):
            prices.load(self.tmp)
        (self.tmp / "evals" / "results" / "prices.json").write_text(json.dumps(PRICES))
        self.assertEqual(prices.load(self.tmp), PRICES)


class Cost(unittest.TestCase):
    def test_each_count_is_priced_at_its_own_rate_and_input_only_for_what_the_cache_did_not_hold(self):
        # model-a: 400,000 plain input at 2, 500,000 cache reads at 0.1, 100,000 writes at 2.5, 10,000 out at 10;
        # model-b: 1,000 plain input at 1 and 1,000 out at 5.
        tokens = {"model-a": counts(1_000_000, 500_000, 100_000, 10_000), "model-b": counts(1_000, output=1_000)}
        self.assertEqual(prices.cost(tokens, PRICES), 1.206)
        self.assertEqual(prices.cost({"model-a": counts(3, output=1)}, PRICES), 0.000016)

    def test_no_counts_or_a_model_with_no_price_gives_no_money_never_a_guess(self):
        self.assertIsNone(prices.cost(None, PRICES))
        self.assertIsNone(prices.cost({"model-a": counts(10), "model-c": counts(10)}, PRICES))

    def test_cache_counts_above_all_input_are_refused(self):
        with self.assertRaisesRegex(prices.PriceError, "exceed"):
            prices.cost({"model-a": counts(10, read=8, write=3)}, PRICES)


if __name__ == "__main__":
    unittest.main()
