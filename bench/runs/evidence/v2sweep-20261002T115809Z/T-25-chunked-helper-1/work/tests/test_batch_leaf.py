"""Tests for utils.batch.chunked.

Pins the shared chunked(seq, size) helper: ordered chunks of at most
`size` items, with the last chunk carrying the remainder.
"""

from utils.batch import chunked


def test_chunked_basic():
    assert chunked([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_chunked_last_chunk_remainder():
    assert chunked([1, 2, 3], 2) == [[1, 2], [3]]


def test_chunked_empty_sequence():
    assert chunked([], 2) == []


def test_chunked_size_one():
    assert chunked([1, 2, 3], 1) == [[1], [2], [3]]


def test_chunked_empty_size():
    assert chunked([1, 2, 3], 0) == []


def test_chunked_returns_lists():
    result = chunked([1, 2, 3], 2)
    assert all(isinstance(chunk, list) for chunk in result)
    assert all(len(chunk) <= 2 for chunk in result)
    assert result == [[1, 2], [3]]
