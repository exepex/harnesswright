from src.cart import total


def test_total():
    assert total([(2, 1.5)]) == 3.0
