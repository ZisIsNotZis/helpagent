# T-08-add-cache-invalidation — solution (never shown to a run)

## Minimal fix

One file: `repo/metrics/registry.py`. The read cache is never invalidated on write, so
a `value()` call before an `increment()` pins a stale number forever. The minimal fix
drops the cached entry on write (the next read re-fills it from the counters dict):

```python
    def increment(self, name: str, by: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + by
        self._cache.pop(name, None)
```

(Equivalent minimal alternative: write the new value through into the cache instead
of dropping the entry. Both keep the cached read path and make writes visible.)

## Red → green

- Ships broken: `cd repo && python -m pytest` → 1 failed
  (`test_write_is_visible_to_the_next_read`: reads 1 after increment by 4 — the
  earlier `value("hits")` call pinned 0 in the cache).
- After the fix: 2 passed.
- Restore the broken state by reverting `repo/metrics/registry.py` to its original
  bytes (SHA-256 checked).

## Untouched contract

Everything except `repo/metrics/registry.py` stays byte-identical — see `UNTOUCHED` in
`checks.py`.
