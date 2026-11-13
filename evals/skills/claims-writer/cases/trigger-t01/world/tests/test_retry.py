import unittest

from src.orders.retry import with_retry


class Retry(unittest.TestCase):
    def test_gives_up_after_three(self):
        calls = []

        def broken():
            calls.append(1)
            raise ConnectionError

        with self.assertRaises(ConnectionError):
            with_retry(broken, wait=0)
        self.assertEqual(len(calls), 3)
