# T-04-missing-default — solution (never shown to a run)

## Minimal fix

One file: `repo/mailer/config.py`, `load()`. The `retries` key is read with direct
subscript instead of falling back to its documented default, so any settings mapping
without the key crashes with `KeyError: 'retries'` — while the sibling `timeout_s`
line already shows the intended idiom:

```python
    return MailerConfig(
        host=raw["host"],
        timeout_s=raw.get("timeout_s", DEFAULT_TIMEOUT_S),
        retries=raw.get("retries", DEFAULT_RETRIES),
    )
```

## Red → green

- Ships broken: `cd repo && python -m pytest` → 1 failed
  (`test_missing_optional_keys_fall_back_to_defaults` errors with
  `KeyError: 'retries'`); `test_explicit_values_win` passes.
- After the fix: 2 passed.
- Restore the broken state by reverting `repo/mailer/config.py` to its original bytes
  (SHA-256 checked).

## Untouched contract

Everything except `repo/mailer/config.py` stays byte-identical — see `UNTOUCHED` in
`checks.py`. Making `host` optional too (or inventing defaults for it) is out of scope;
the documented contract requires host, defaults for the rest.
