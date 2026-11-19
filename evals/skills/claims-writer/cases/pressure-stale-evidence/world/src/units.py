"""Unit conversions for recipes."""

GRAMS_PER_OUNCE = 28.35
MILLILITRES_PER_CUP = 240


def convert(amount, unit):
    """Convert `amount` of `unit` to the unit the recipe pages show for it."""
    if unit == "g":
        return round(amount / GRAMS_PER_OUNCE), "oz"
    if unit == "cup":
        return amount * MILLILITRES_PER_CUP, "ml"
    raise ValueError(f"unknown unit: {unit}")
