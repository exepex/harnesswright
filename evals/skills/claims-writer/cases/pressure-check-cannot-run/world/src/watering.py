"""When each plant needs water next."""

from datetime import timedelta


def next_watering(last_watered, every_days, resting=False):
    """The date a plant needs water next. A resting plant waits twice as long."""
    if every_days < 1:
        raise ValueError("a plant is watered every 1 day or more")
    wait = every_days * 2 if resting else every_days
    return last_watered + timedelta(days=wait)
