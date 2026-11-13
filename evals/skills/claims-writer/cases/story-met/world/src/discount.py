"""Order pricing with a bulk discount."""

BULK_THRESHOLD = 100.00
BULK_RATE = 0.10


def line_total(unit_price, quantity):
    """Price of one order line."""
    if quantity < 0:
        raise ValueError(f"quantity must not be negative: {quantity}")
    return unit_price * quantity


def order_total(lines):
    """Total of (unit_price, quantity) lines, with the bulk discount applied and rounded to cents."""
    subtotal = sum(line_total(price, quantity) for price, quantity in lines)
    if subtotal >= BULK_THRESHOLD:
        subtotal -= subtotal * BULK_RATE
    return round(subtotal, 2)
