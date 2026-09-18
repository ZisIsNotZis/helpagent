"""Sliding-window contract tests."""

from limiter.window import SlidingWindowLimiter


def test_burst_within_limit_passes():
    lim = SlidingWindowLimiter(limit=3, window_s=10)
    assert [lim.allow(t) for t in (0, 1, 2)] == [True, True, True]


def test_limit_exceeded_in_window():
    lim = SlidingWindowLimiter(limit=3, window_s=10)
    assert [lim.allow(t) for t in (0, 1, 2, 3)] == [True, True, True, False]


def test_window_slides_forward():
    lim = SlidingWindowLimiter(limit=3, window_s=10)
    assert [lim.allow(t) for t in (0, 1, 2)] == [True, True, True]
    assert lim.allow(10.5) is True   # t=0 left the window
    assert lim.allow(11.0) is True   # t=1 left the window
    assert lim.allow(11.1) is False  # 2,10.5,11.0 still within 10s


def test_rejected_calls_do_not_consume_budget():
    lim = SlidingWindowLimiter(limit=2, window_s=10)
    assert lim.allow(0) is True and lim.allow(1) is True
    assert lim.allow(2) is False     # rejected
    assert lim.allow(2.5) is False   # still 2 calls inside the window
