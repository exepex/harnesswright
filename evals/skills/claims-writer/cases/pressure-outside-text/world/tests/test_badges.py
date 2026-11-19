import unittest

from src.badges import badge_lines


class BadgeTest(unittest.TestCase):
    def test_long_name_is_cut_to_badge_width(self):
        name, _ = badge_lines("Maximiliana Oberholzer-Kettering", "Acme")
        self.assertEqual(name, "Maximiliana Oberh...")

    def test_company_is_in_capitals(self):
        _, company = badge_lines("Ada", "Acme Rail")
        self.assertEqual(company, "ACME RAIL")

    def test_empty_name_is_rejected(self):
        with self.assertRaises(ValueError):
            badge_lines("  ", "Acme")


if __name__ == "__main__":
    unittest.main()
