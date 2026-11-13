import unittest

from src.catalog.paging import page


class Paging(unittest.TestCase):
    def test_twenty_per_page(self):
        self.assertEqual(len(page(list(range(45)), 1)), 20)

    def test_past_the_end(self):
        self.assertEqual(page(list(range(45)), 4), [])
