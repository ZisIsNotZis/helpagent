# A-03-book-store - reference solution (never shown to a run)

Provenance: tests + instructions from exercism/python@1f6aab8667bf653b10cc3799f94352fcdb749db6 (MIT), exercises/practice/book-store; tests auto-generated from problem-specifications canonical data. Reference solution: ours, verified against the official tests below.

Tier: hard.

```python
"""Basket pricing with group discounts (Exercism book-store)."""

PRICE = 800
DISCOUNTS = [0, 0, 5, 10, 20, 25]  # percent off per distinct-group size 0..5


def _best(counts, memo):
    key = tuple(counts)
    if key in memo:
        return memo[key]
    if sum(counts) == 0:
        return 0
    distinct = sum(1 for c in counts if c > 0)
    best = None
    for size in range(min(5, distinct), 0, -1):
        order = sorted(range(len(counts)), key=lambda i: -counts[i])[:size]
        nxt = list(counts)
        for i in order:
            nxt[i] -= 1
        nxt = sorted(nxt, reverse=True)
        cost = size * PRICE * (100 - DISCOUNTS[size]) // 100 + _best(nxt, memo)
        if best is None or cost < best:
            best = cost
    memo[key] = best
    return best


def total(basket):
    counts = [0] * 5
    for isbn in basket:
        counts[isbn - 1] += 1
    return _best(counts, {})

```
