from src.wishlist import add


def test_add_twice():
    assert add(add([], "p1"), "p1") == ["p1"]
