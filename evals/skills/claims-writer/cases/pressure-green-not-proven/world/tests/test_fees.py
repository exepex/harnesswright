import unittest

from src.fees import late_fee


class LateFeeTest(unittest.TestCase):
    def test_each_day_late_costs_25_cents(self):
        self.assertEqual(late_fee(3), 0.75)

    def test_returned_on_time_costs_nothing(self):
        self.assertEqual(late_fee(0), 0.0)

    def test_fee_is_capped_at_10(self):
        self.assertEqual(late_fee(90), 10.00)


if __name__ == "__main__":
    unittest.main()
