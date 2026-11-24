import unittest

from src.loyalty import free_drinks, points_for


class PointsTest(unittest.TestCase):
    def test_each_whole_euro_earns_ten_points(self):
        self.assertEqual(points_for(1299), 120)

    def test_a_negative_bill_is_refused(self):
        with self.assertRaises(ValueError):
            points_for(-1)

    def test_five_hundred_points_pay_for_one_drink(self):
        self.assertEqual(free_drinks(1099), 2)


if __name__ == "__main__":
    unittest.main()
