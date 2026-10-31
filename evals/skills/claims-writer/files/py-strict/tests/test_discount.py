import unittest

from src.discount import line_total, order_total


class OrderTotalTest(unittest.TestCase):
    def test_subtotal_of_exactly_100_gets_ten_percent_off(self):
        self.assertEqual(order_total([(25.00, 4)]), 90.00)

    def test_subtotal_below_100_gets_no_discount(self):
        self.assertEqual(order_total([(33.00, 3)]), 99.00)

    def test_total_is_rounded_to_cents(self):
        self.assertEqual(order_total([(0.333, 3)]), 1.00)

    def test_negative_quantity_is_rejected(self):
        with self.assertRaises(ValueError):
            line_total(5.00, -1)


if __name__ == "__main__":
    unittest.main()
