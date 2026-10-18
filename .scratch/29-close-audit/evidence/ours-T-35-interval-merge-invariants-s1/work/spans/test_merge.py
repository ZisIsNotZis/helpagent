"""Test merge of half-open intervals.

Contract: result is sorted, non-overlapping, and TOUCHING intervals merge.
Empty intervals are dropped.
"""


def test_merge_touches_merge():
    assert merge([[1, 3], [3, 5]]) == [[1, 5]]


def test_merge_sorted_non_overlapping():
    assert merge([[1, 2], [3, 4], [5, 6]]) == [[1, 2], [3, 4], [5, 6]]


def test_merge_empty_dropped():
    assert merge([[1, 1], [2, 3]]) == [[2, 3]]


def test_merge_unsorted():
    assert merge([[3, 4], [1, 2], [2, 3]]) == [[1, 2], [2, 3]]


def test_merge_multiple_touches():
    assert merge([[1, 3], [2, 4], [4, 5]]) == [[1, 5]]
