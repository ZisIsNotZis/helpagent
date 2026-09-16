"""Per-key throttle with a configurable threshold."""


class Limiter:
    """Allows up to ``threshold`` hits per key, then blocks.

    ``on_limit`` is an optional callback invoked as ``on_limit(key)`` — callers use
    it for paging/alerting. It fires once per key, when the key first crosses the
    threshold; later blocked hits do not re-fire it. ``None`` disables it.
    """

    def __init__(self, threshold: int, on_limit=None) -> None:
        self.threshold = threshold
        self.on_limit = on_limit
        self._counts: dict[str, int] = {}
        self._blocked: set[str] = set()

    def hit(self, key: str) -> bool:
        """Record one hit for ``key``; True when the hit is allowed."""
        count = self._counts.get(key, 0) + 1
        self._counts[key] = count
        if count > self.threshold:
            self._blocked.add(key)
        return count <= self.threshold
