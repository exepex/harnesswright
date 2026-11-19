import unittest

from src.overtime import weekly_pay


class WeeklyPayTest(unittest.TestCase):
    def test_forty_hours_are_paid_at_the_plain_wage(self):
        self.assertEqual(weekly_pay(20.00, 40), 800.00)

    def test_hours_past_forty_earn_time_and_a_half(self):
        self.assertEqual(weekly_pay(20.00, 45), 950.00)

    def test_sunday_hours_earn_double(self):
        self.assertEqual(weekly_pay(20.00, 40, sunday_hours=5), 1000.00)

    def test_negative_hours_are_rejected(self):
        with self.assertRaises(ValueError):
            weekly_pay(20.00, -1)


if __name__ == "__main__":
    unittest.main()
