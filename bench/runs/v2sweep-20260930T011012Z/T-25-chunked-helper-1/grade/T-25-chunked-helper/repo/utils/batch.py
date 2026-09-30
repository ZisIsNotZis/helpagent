"""Shared batching helpers.

Three call sites need chunked(): feed a sequence and a size, get lists of at
most `size` items, in order, with the last chunk carrying the remainder.
"""


def chunked(seq, size: int):
    if size <= 0:
        return []
    chunks = []
    for i in range(0, len(seq), size):
        chunks.append(seq[i:i + size])
    return chunks
