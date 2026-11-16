import unittest

from src.discount import apply


class Discount(unittest.TestCase):
    def test_takes_off_the_percent(self):
        self.assertEqual(apply(1000, 10), 900)

    def test_refuses_more_than_all(self):
        with self.assertRaises(ValueError):
            apply(1000, 101)
