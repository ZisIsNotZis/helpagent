# T-02-off-by-one — solution (never shown to a run)

## Minimal fix

One file: `repo/catalog/pagination.py`, `paginate()`. The page end index forgets that
Python slices are end-exclusive, so every page drops its last item and the dropped items
never appear on any page:

```python
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end]
```

## Red → green

- Ships broken: `cd repo && python -m pytest` → 2 failed
  (`test_first_page_returns_per_page_items`, `test_consecutive_pages_are_contiguous`);
  `test_last_page_returns_remainder` and `test_total_pages_rounds_up` pass pre-fix —
  the clamped final page coincidentally works, and `total_pages` is not the bug.
- After the fix: 4 passed.
- Restore the broken state by reverting `repo/catalog/pagination.py` to its original
  bytes (SHA-256 checked).

## Untouched contract

Everything except `repo/catalog/pagination.py` stays byte-identical — see `UNTOUCHED`
in `checks.py`. Weakening the tests instead of fixing the slice is a contract violation.
