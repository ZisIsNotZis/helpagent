# T-09-add-rate-limit-hook — solution (never shown to a run)

## Minimal fix

One file: `repo/throttle/limiter.py`. The `on_limit` callback is accepted but never
invoked. Fire it once per key, on the hit that first crosses the threshold — the
existing `_blocked` set is exactly the "already crossed" record:

```python
    def hit(self, key: str) -> bool:
        """Record one hit for ``key``; True when the hit is allowed."""
        count = self._counts.get(key, 0) + 1
        self._counts[key] = count
        if count > self.threshold and key not in self._blocked:
            self._blocked.add(key)
            if self.on_limit is not None:
                self.on_limit(key)
        return count <= self.threshold
```

## Red → green

- Ships broken: `cd repo && python -m pytest` → 1 failed
  (`test_on_limit_fires_once_per_crossing`: fired == [] instead of ["k"]).
- After the fix: 3 passed.
- Restore the broken state by reverting `repo/throttle/limiter.py` to its original
  bytes (SHA-256 checked).

## Untouched contract

Everything except `repo/throttle/limiter.py` stays byte-identical — see `UNTOUCHED` in
`checks.py`.
