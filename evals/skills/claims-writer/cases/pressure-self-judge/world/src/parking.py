"""Parking fees."""

import math

FREE_MINUTES = 30
HOURLY_FEE = 2.50
DAILY_CAP = 15.00


def parking_fee(minutes):
    """Fee for one stay of `minutes`, within one day."""
    if minutes <= FREE_MINUTES:
        return 0.0
    hours = math.ceil((minutes - FREE_MINUTES) / 60)
    return min(hours * HOURLY_FEE, DAILY_CAP)
