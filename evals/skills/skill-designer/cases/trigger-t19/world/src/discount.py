def apply(cents, percent):
    if not 0 <= percent <= 100:
        raise ValueError(percent)
    return cents - cents * percent // 100
