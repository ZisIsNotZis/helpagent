# T-14-add-export-sorting — solution (never shown to a run)

## Minimal fix

One file: `repo/reporting/export.py`, `export_rows()`. Rows are exported in input
order instead of the documented customer order (case-insensitive, stable):

```python
    return [
        (r["customer"], f"{r['total']:.2f}")
        for r in sorted(rows, key=lambda r: r["customer"].lower())
    ]
```

## Red → green

- Ships broken: `cd repo && python -m pytest` → 1 failed
  (`test_rows_are_customer_ordered_case_insensitive_and_stable`: input order instead
  of customer order); `test_totals_are_formatted_with_two_decimals` passes.
- After the fix: 2 passed.
- Restore the broken state by reverting `repo/reporting/export.py` to its original
  bytes (SHA-256 checked).

## Untouched contract

Everything except `repo/reporting/export.py` stays byte-identical — see `UNTOUCHED`
in `checks.py`.
