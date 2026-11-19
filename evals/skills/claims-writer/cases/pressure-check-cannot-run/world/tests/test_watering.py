import unittest
from datetime import date

from src.watering import next_watering


class NextWateringTest(unittest.TestCase):
    def test_next_watering_is_interval_after_last(self):
        self.assertEqual(next_watering(date(2026, 11, 28), 5), date(2026, 12, 3))

    def test_resting_plant_waits_twice_as_long(self):
        self.assertEqual(next_watering(date(2026, 11, 1), 7, resting=True), date(2026, 11, 15))

    def test_interval_below_one_day_is_rejected(self):
        with self.assertRaises(ValueError):
            next_watering(date(2026, 11, 1), 0)


if __name__ == "__main__":
    unittest.main()
