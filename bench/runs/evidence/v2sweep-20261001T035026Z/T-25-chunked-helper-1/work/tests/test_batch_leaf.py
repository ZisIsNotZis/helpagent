"""Tests for utils.batch.chunked."""

from utils.batch import chunked


def test_chunked_basic():
    seq = [1, 2, 3, 4, 5]
    assert chunked(seq, 2) == [[1, 2], [3, 4], [5]]


def test_chunked_last_chunk_remainder():
    seq = [1, 2, 3, 4, 5]
    assert chunked(seq, 3) == [[1, 2, 3], [4, 5]]


def test_chunked_size_one():
    seq = [1, 2, 3, 4]
    assert chunked(seq, 1) == [[1], [2], [3], [4]]


def test_chunked_empty():
    assert chunked([], 2) == []


def test_chunked_empty_size():
    assert chunked([1, 2], 0) == []
