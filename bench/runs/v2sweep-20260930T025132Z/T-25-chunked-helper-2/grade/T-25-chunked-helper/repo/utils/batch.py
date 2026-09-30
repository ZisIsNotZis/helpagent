"""Shared batching helpers.

Three call sites need chunked(): feed a sequence and a size, get lists of at
most `size` items, in order, with the last chunk carrying the remainder.
"""


def chunked(seq, size: int):
    if size <= 0:
        return []
    return [seq[i:i + size] for i in range(0, len(seq), size)]
