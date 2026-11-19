"""The text printed on a conference name badge."""

WIDTH = 20


def badge_lines(name, company):
    """The two lines of a badge: the name, cut to fit, and the company in capitals."""
    if not name.strip():
        raise ValueError("a badge needs a name")
    if len(name) > WIDTH:
        name = name[:WIDTH - 2] + "..."
    return name, company.upper()
