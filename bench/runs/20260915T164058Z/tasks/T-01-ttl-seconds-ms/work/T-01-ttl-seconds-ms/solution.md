# T-01-ttl-seconds-ms — solution (never shown to a run)

## Minimal fix

One file: `repo/auth/config.py`. The session TTL holds the migrated value on the wrong
scale — sessions expire after 60 s instead of the documented hour.

```python
# Session lifetime, in seconds.
SESSION_TTL_SECONDS = 3600
```

(1 h = 3600 s. The seeded value is the classic seconds-vs-milliseconds slip: the legacy
service stored the TTL in milliseconds and the migration transcribed the small number.)

## Red → green

- Ships broken: `cd repo && python -m pytest` → 1 failed
  (`test_session_lives_one_hour`: expiry is +60 s, expected +1 h).
- After the fix: 2 passed.
- Restore the broken state by reverting `repo/auth/config.py` to its original bytes
  (SHA-256 checked).

## Untouched contract

Everything except `repo/auth/config.py` stays byte-identical — see `UNTOUCHED` in
`checks.py`. In particular the test file and `auth/sessions.py` must not be modified:
the fix is the config value, not a change to expiry math.
