import unittest

from src.giftcard import apply


class GiftCard(unittest.TestCase):
    def test_partial(self):
        self.assertEqual(apply(10, 25), (10, 15))
