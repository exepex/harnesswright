import unittest

from src.parking import parking_fee


class ParkingFeeTest(unittest.TestCase):
    def test_first_half_hour_is_free(self):
        self.assertEqual(parking_fee(30), 0.0)

    def test_each_started_hour_after_that_costs_2_50(self):
        self.assertEqual(parking_fee(31), 2.50)
        self.assertEqual(parking_fee(150), 5.00)

    def test_a_day_costs_at_most_15(self):
        self.assertEqual(parking_fee(600), 15.00)


if __name__ == "__main__":
    unittest.main()
