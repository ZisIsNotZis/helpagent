"""Counters registry with a read cache for hot paths."""


class Registry:
    """Counters with a cached read path.

    Reads are served from a cache so hot dashboards do not re-read the counters
    dict on every scrape; a write must always be visible to the very next read.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._cache: dict[str, int] = {}

    def increment(self, name: str, by: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + by
        self._cache.pop(name, None)

    def value(self, name: str) -> int:
        """Current value of counter ``name`` (cached read path)."""
        if name not in self._cache:
            self._cache[name] = self._counters.get(name, 0)
        return self._cache[name]
