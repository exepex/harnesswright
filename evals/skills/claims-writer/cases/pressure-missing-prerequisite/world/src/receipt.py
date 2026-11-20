"""The till receipt."""


def receipt_lines(items):
    """One line per item, name and price in euros, then the total."""
    lines = [f"{name:<20}{cents / 100:>8.2f}" for name, cents in items]
    total = sum(cents for _, cents in items)
    return lines + [f"{'Total':<20}{total / 100:>8.2f}"]
