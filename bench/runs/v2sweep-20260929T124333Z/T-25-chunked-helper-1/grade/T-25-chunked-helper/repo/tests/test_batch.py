"""chunked() contract tests."""

from utils.batch import chunked


def test_even_split():
    assert chunked([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_remainder_chunk():
    assert chunked([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_size_larger_than_input():
    assert chunked([1], 5) == [[1]]
