"""Invoice lines and totals, in cents."""

VAT_PERCENT = 20


def line_net(unit_cents, quantity):
    """The net amount of one invoice line."""
    if quantity < 0:
        raise ValueError("quantity cannot be negative")
    return unit_cents * quantity


def line_vat(net_cents):
    """The VAT on one line's net amount."""
    return net_cents * VAT_PERCENT // 100


def invoice_total(nets):
    """The total of an invoice: each line's net amount and its VAT."""
    return sum(net + line_vat(net) for net in nets)
