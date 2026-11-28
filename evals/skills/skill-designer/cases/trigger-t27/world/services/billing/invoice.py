"""Render an invoice as text."""

from services.billing.flags import enabled


def render(invoice):
    if enabled("new_invoice_layout"):
        lines = [f"Invoice {invoice['number']}", f"Total due: {invoice['total']}"]
    else:
        lines = [f"INVOICE NO. {invoice['number']}", f"TOTAL {invoice['total']}"]
    return "\n".join(lines)
