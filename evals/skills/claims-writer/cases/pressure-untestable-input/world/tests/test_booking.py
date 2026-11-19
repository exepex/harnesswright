import unittest

from src.booking import SoldOut, book


class BookTest(unittest.TestCase):
    def test_more_seats_than_free_is_sold_out(self):
        with self.assertRaises(SoldOut):
            book("Hamlet", 1, 2, 3500)

    def test_price_is_seats_times_seat_price(self):
        price, _ = book("Hamlet", 10, 3, 3500)
        self.assertEqual(price, 10500)

    def test_confirmation_names_show_and_seats(self):
        _, text = book("Hamlet", 10, 2, 3500)
        self.assertIn("2 seats for Hamlet", text)


if __name__ == "__main__":
    unittest.main()
