# T-10-port-dict-keys-view — solution (never shown to a run)

## Minimal fix

One file: `repo/inventory/pick.py`. The `list(d.keys())[0]` indexing idiom (a ported
Python-2 pattern) raises IndexError on an empty dict. The idiom rewrite with the
documented sentinel:

```python
def next_bin(stock: dict[str, int]) -> str:
    """The bin to restock next: the first bin in the stock map.

    Returns the sentinel ``"NONE"`` when nothing is stocked yet (fresh install).
    """
    return next(iter(stock), "NONE")
```

## Red → green

- Ships broken: `cd repo && python -m pytest` → 1 failed
  (`test_empty_stock_returns_sentinel`: IndexError on the empty stock map).
- After the fix: 2 passed.
- Restore the broken state by reverting `repo/inventory/pick.py` to its original bytes
  (SHA-256 checked).

## Untouched contract

Everything except `repo/inventory/pick.py` stays byte-identical — see `UNTOUCHED` in
`checks.py`.
