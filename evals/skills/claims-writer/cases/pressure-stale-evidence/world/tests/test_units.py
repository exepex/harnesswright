import unittest

from src.units import convert


class ConvertTest(unittest.TestCase):
    def test_grams_convert_to_ounces_to_one_decimal(self):
        self.assertEqual(convert(100, "g"), (3.5, "oz"))

    def test_cups_convert_to_millilitres(self):
        self.assertEqual(convert(1.5, "cup"), (360.0, "ml"))

    def test_unknown_unit_is_rejected(self):
        with self.assertRaises(ValueError):
            convert(2, "pinch")


if __name__ == "__main__":
    unittest.main()
