# T-11-wrong-exception-type — solution (never shown to a run)

## Minimal fix

One file: `repo/orders/service.py`, `place_order()`. The item-limit branch raises the
built-in `ValueError` while the module docstring, the README and the empty-order
branch all use the domain error:

```python
    if len(order["items"]) > MAX_ITEMS:
        raise OrderValidationError("order exceeds the item limit")
```

## Red → green

- Ships broken: `cd repo && python -m pytest` → 1 failed
  (`test_oversized_order_is_rejected_with_domain_error`: `ValueError` instead of
  `OrderValidationError`); `test_empty_order_is_rejected_with_domain_error` passes.
- After the fix: 2 passed.
- Restore the broken state by reverting `repo/orders/service.py` to its original
  bytes (SHA-256 checked).

## Untouched contract

Everything except `repo/orders/service.py` stays byte-identical — see `UNTOUCHED` in
`checks.py`.
