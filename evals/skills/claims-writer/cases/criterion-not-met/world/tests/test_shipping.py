import unittest

from src.shipping import shipping_fee


class ShippingFeeTest(unittest.TestCase):
    def test_standard_fee_below_free_threshold(self):
        self.assertEqual(shipping_fee(49.99, "DE"), 4.90)

    def test_standard_is_free_from_50(self):
        self.assertEqual(shipping_fee(50.00, "FR"), 0.0)

    def test_express_costs_twice_the_standard_fee(self):
        self.assertEqual(shipping_fee(20.00, "NL", express=True), 9.80)

    def test_unserved_country_is_rejected(self):
        with self.assertRaises(ValueError):
            shipping_fee(20.00, "US")


if __name__ == "__main__":
    unittest.main()
