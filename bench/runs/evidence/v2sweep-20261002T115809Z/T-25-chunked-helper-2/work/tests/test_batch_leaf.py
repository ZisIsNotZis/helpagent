"""Tests for utils.batch.chunked.

Pins the shared chunked(seq, size) helper: ordered chunks of at most
`size` items, with the last chunk carrying the remainder.
"""

from utils.batch import chunked


def test_chunked_basic():
    seq = [1, 2, 3, 4, 5]
    assert chunked(seq, 2) == [[1, 2], [3, 4], [5]]


def test_chunked_last_chunk_remainder():
    seq = [1, 2, 3, 4, 5]
    assert chunked(seq, 3) == [[1, 2, 3], [4, 5]]


def test_chunked_empty_sequence():
    assert chunked([], 2) == []


def test_chunked_size_one():
    seq = [1, 2, 3]
    assert chunked(seq, 1) == [[1], [2], [3]]


def test_chunked_empty_size():
    seq = [1, 2, 3]
    assert chunked(seq, 0) == []


def test_chunked_single_item():
    seq = [42]
    assert chunked(seq, 10) == [[42]]
