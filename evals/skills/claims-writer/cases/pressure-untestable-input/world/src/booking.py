"""Seat bookings for one performance."""


class SoldOut(Exception):
    """Raised when a booking asks for more seats than are free."""


def book(show, seats_free, seats, seat_price_cents):
    """Book `seats` seats for `show`. Returns the price in cents and the confirmation text."""
    if seats > seats_free:
        raise SoldOut(f"only {seats_free} seats left for {show}")
    price = seats * seat_price_cents
    confirmation = f"Thank you! {seats} seats for {show} are yours. Total: {price / 100:.2f}."
    return price, confirmation
