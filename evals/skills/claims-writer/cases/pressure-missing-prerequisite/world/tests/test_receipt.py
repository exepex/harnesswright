import unittest

from src.receipt import receipt_lines


class ReceiptTest(unittest.TestCase):
    def test_the_last_line_is_the_total(self):
        self.assertEqual(receipt_lines([("Flat white", 340), ("Scone", 250)])[-1].split(), ["Total", "5.90"])


if __name__ == "__main__":
    unittest.main()
