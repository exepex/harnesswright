"""Late fees for loans."""

FEE_PER_DAY = 0.25
FEE_CAP = 10.00


def late_fee(days_late, card_type="adult"):
    """Fee for returning one loan `days_late` days after its due date."""
    if card_type == "child" or days_late <= 0:
        return 0.0
    return min(days_late * FEE_PER_DAY, FEE_CAP)
