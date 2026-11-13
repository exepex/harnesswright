"""Shipping fees."""

STANDARD_FEE = 4.90
FREE_FROM = 50.00
COUNTRIES = ("DE", "FR", "NL")


def shipping_fee(order_total, country, express=False):
    """Fee for shipping an order of `order_total` to `country`."""
    fee = 0.0 if order_total >= FREE_FROM else STANDARD_FEE
    if express:
        fee *= 2
    return fee
