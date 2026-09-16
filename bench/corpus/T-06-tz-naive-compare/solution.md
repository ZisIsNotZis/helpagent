# T-06-tz-naive-compare — solution (never shown to a run)

## Minimal fix

One file: `repo/scheduler/jobs.py`. The default clock uses the naive `datetime.utcnow()`
while every stored timestamp is timezone-aware UTC — comparing the two raises
`TypeError: can't compare offset-naive and offset-aware datetimes`.

```python
def is_due(job: dict, now: datetime | None = None) -> bool:
    """True when ``job``'s next_run has passed at ``now`` (UTC now by default)."""
    now = now or datetime.now(timezone.utc)
    return job["next_run"] <= now
```

(`datetime.utcnow()` is also deprecated since 3.12; the aware constructor is the
documented convention for this module.)

## Red → green

- Ships broken: `cd repo && python -m pytest` → 1 failed
  (`test_due_check_works_with_the_default_clock`: TypeError on the naive/aware compare).
- After the fix: 2 passed.
- Restore the broken state by reverting `repo/scheduler/jobs.py` to its original bytes
  (SHA-256 checked).

## Untouched contract

Everything except `repo/scheduler/jobs.py` stays byte-identical — see `UNTOUCHED` in
`checks.py`.
