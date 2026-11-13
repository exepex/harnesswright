from src.pricing import discounted


def test_ten_percent():
    assert discounted(20.0, 10) == 18.0
