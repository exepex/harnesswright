"""Weekly pay with overtime."""

REGULAR_HOURS = 40
OVERTIME_RATE = 1.5
SUNDAY_RATE = 2.0


def weekly_pay(hourly_wage, weekday_hours, sunday_hours=0):
    """Pay for one week: weekday hours past 40 earn time and a half, Sunday hours earn double."""
    if hourly_wage < 0 or weekday_hours < 0 or sunday_hours < 0:
        raise ValueError("wage and hours must not be negative")
    regular = min(weekday_hours, REGULAR_HOURS)
    overtime = weekday_hours - regular
    pay = regular * hourly_wage + overtime * hourly_wage * OVERTIME_RATE
    pay += sunday_hours * hourly_wage * SUNDAY_RATE
    return round(pay, 2)
