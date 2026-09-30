# T-03-wrong-comparison — solution (never shown to a run)

## Minimal fix

One file: `repo/billing/plans.py`, `is_enterprise()`. The plan string is compared by
identity instead of by equality; webhook values are runtime-built strings (parsed,
stripped, lowercased), so they are never the same object as the module-level constant
and the check silently returns False:

```python
def is_enterprise(plan: str) -> bool:
    """True when ``plan`` is the enterprise plan."""
    return plan == PLAN_ENTERPRISE
```

(`is_known` already uses membership over a tuple, i.e. `==` semantics, which is why the
same payload matches there — matching the report's "checks by hand work, webhooks don't".)

## Red → green

- Ships broken: `cd repo && python -m pytest` → 1 failed
  (`test_enterprise_detected_from_webhook_payload`); the other two pass — they only
  exercise `==`-compatible paths, so the bug is pinned to webhook-parsed values.
- After the fix: 3 passed.
- Restore the broken state by reverting `repo/billing/plans.py` to its original bytes
  (SHA-256 checked).

## Untouched contract

Everything except `repo/billing/plans.py` stays byte-identical — see `UNTOUCHED` in
`checks.py`. Rewriting `parse_webhook` to return the interned constant (defeating the
test instead of fixing the comparison) violates the contract.
