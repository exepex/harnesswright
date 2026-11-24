"""Loyalty points for the café till."""

POINTS_PER_EURO = 10
FREE_DRINK_POINTS = 500


def points_for(total_cents):
    """Points earned on a bill: 10 for each whole euro."""
    if total_cents < 0:
        raise ValueError("a bill cannot be negative")
    return total_cents // 100 * POINTS_PER_EURO


def free_drinks(points):
    """How many free drinks a balance of points pays for."""
    return max(points, 0) // FREE_DRINK_POINTS
