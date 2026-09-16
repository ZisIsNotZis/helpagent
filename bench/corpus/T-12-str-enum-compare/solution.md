# T-12-str-enum-compare — solution (never shown to a run)

## Minimal fix

One file: `repo/access/gate.py`, `can_publish()`. The whitelist membership test
compares by identity, so a role parsed from a webhook header (a fresh `Role`
instance) never matches the `Role.EDITOR`/`Role.ADMIN` class attributes — while a
session-carried `Role.EDITOR` does. Value comparison makes both doors behave the
same:

```python
def can_publish(author: Author) -> bool:
    """True when ``author``'s role is in the publishing whitelist."""
    return any(author.role == r for r in _PUBLISH_ALLOWED)
```

## Red → green

- Ships broken: `cd repo && python -m pytest` → 1 failed
  (`test_webhook_parsed_editor_may_publish`: `can_publish` is `False` for the
  parsed editor); the session path and the viewer test pass.
- After the fix: 3 passed.
- Restore the broken state by reverting `repo/access/gate.py` to its original
  bytes (SHA-256 checked).

## Untouched contract

Everything except `repo/access/gate.py` stays byte-identical — see `UNTOUCHED` in
`checks.py`. The README documents the equality requirement; roles.py (the type
itself) is not part of any fix.
