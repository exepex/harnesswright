import unittest

from src.brew import brew_seconds


class BrewTest(unittest.TestCase):
    def test_black_tea_brews_four_minutes(self):
        self.assertEqual(brew_seconds("black"), 240)

    def test_green_and_herbal_tea_brew_two_and_five_minutes(self):
        self.assertEqual((brew_seconds("green"), brew_seconds("herbal")), (120, 300))

    def test_a_strong_pot_brews_a_minute_longer(self):
        self.assertEqual(brew_seconds("green", strong=True), 180)

    def test_an_unknown_tea_is_refused(self):
        with self.assertRaises(ValueError):
            brew_seconds("oolong")


if __name__ == "__main__":
    unittest.main()
