# A-01-word-count - reference solution (never shown to a run)

Provenance: tests + instructions from exercism/python@1f6aab8667bf653b10cc3799f94352fcdb749db6 (MIT), exercises/practice/word-count; tests auto-generated from problem-specifications canonical data. Reference solution: ours, verified against the official tests below.

Tier: easy.

```python
"""Count occurrences of words in a phrase (Exercism word-count)."""

import re


def count_words(sentence: str) -> dict:
    words = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", sentence.lower())
    counts: dict = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    return counts

```
