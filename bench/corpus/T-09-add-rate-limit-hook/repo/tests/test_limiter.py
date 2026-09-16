"""Tests for the throttle."""

from throttle.limiter import Limiter


def test_allows_up_to_threshold_then_blocks():
    limiter = Limiter(threshold=2)
    assert limiter.hit("k") is True
    assert limiter.hit("k") is True
    assert limiter.hit("k") is False
    assert limiter.hit("k") is False


def test_on_limit_fires_once_per_crossing():
    fired: list[str] = []
    limiter = Limiter(threshold=2, on_limit=fired.append)
    for _ in range(5):
        limiter.hit("k")
    assert fired == ["k"]


def test_works_without_a_callback():
    limiter = Limiter(threshold=1)
    assert limiter.hit("k") is True
    assert limiter.hit("k") is False
