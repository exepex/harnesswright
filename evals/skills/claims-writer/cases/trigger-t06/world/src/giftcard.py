def apply(balance, total):
    if balance <= 0:
        raise ValueError("empty card")
    paid = min(balance, total)
    return paid, total - paid
