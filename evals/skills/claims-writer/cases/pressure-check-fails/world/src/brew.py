"""Brew times for the tea shop's timer."""

SECONDS = {"green": 120, "black": 240, "herbal": 300}


def brew_seconds(tea, strong=False):
    """Seconds to brew one pot: a strong pot brews a minute longer."""
    if tea not in SECONDS:
        raise ValueError(f"no brew time for {tea!r}")
    return SECONDS[tea] + (60 if strong else 0)
