def add(items, product):
    if product in items:
        return items
    return items + [product]
