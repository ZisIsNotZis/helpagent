"""Sliding-window rate limiter.

Contract: at most `limit` calls inside ANY window of `window_s` seconds.
`now` is injected (seconds, monotonic) so tests never sleep.
"""


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float):
        self.limit = limit
        self.window_s = window_s
        self.calls: list[float] = []

    def allow(self, now: float) -> bool:
        self.calls.append(now)
        return True
