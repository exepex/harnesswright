from src.search.limit import Limiter


def test_eleventh_is_refused():
    limiter = Limiter()
    results = [limiter.allow("c") for _ in range(11)]
    assert results[-1] is False
