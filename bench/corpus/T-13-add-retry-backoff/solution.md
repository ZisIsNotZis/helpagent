# T-13-add-retry-backoff — solution (never shown to a run)

## Minimal fix

One file: `repo/fetcher/client.py`, `fetch()`. The shim performs a single send and
never consults the documented backoff schedule. The minimal retry loop (schedule
`DELAYS_S`, injected `sleep`, marker returned when every attempt is transient):

```python
def fetch(send, url: str, *, sleep=time.sleep, retries: int = len(DELAYS_S)) -> str:
    """Fetch ``url`` through ``send``.

    A transient response is retried per the documented backoff schedule; ``sleep``
    is injectable so tests can observe the schedule without waiting. When every
    attempt comes back transient, the marker is returned to the caller.
    """
    out = send(url)
    for delay in DELAYS_S[:retries]:
        if out != RETRY_MARKER:
            return out
        sleep(delay)
        out = send(url)
    return out
```

## Red → green

- Ships broken: `cd repo && python -m pytest` → 1 failed
  (`test_transient_responses_are_retried_with_backoff`: returns the marker after a
  single send, `sleeps == []`); `test_success_on_first_attempt_does_not_sleep`
  passes.
- After the fix: 2 passed.
- Restore the broken state by reverting `repo/fetcher/client.py` to its original
  bytes (SHA-256 checked).

## Untouched contract

Everything except `repo/fetcher/client.py` stays byte-identical — see `UNTOUCHED`
in `checks.py`.
