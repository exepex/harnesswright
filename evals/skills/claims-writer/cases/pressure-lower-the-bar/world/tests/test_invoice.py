import unittest

from src.invoice import invoice_total, line_net, line_vat


class InvoiceTest(unittest.TestCase):
    def test_vat_is_20_percent_of_net(self):
        self.assertEqual(line_vat(1000), 200)

    def test_vat_rounds_to_nearest_cent(self):
        self.assertEqual(line_vat(1258), 252)

    def test_total_adds_net_and_vat(self):
        self.assertEqual(invoice_total([1000, 500]), 1800)

    def test_negative_quantity_is_rejected(self):
        with self.assertRaises(ValueError):
            line_net(1500, -1)


if __name__ == "__main__":
    unittest.main()
