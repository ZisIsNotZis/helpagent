import pytest

from spans.merge import merge


def test_ac1_overlapping_merged():
    """AC1: Overlapping spans must be merged, not left separate."""
    intervals = [[1, 3], [2, 4], [3, 5]]
    assert merge(intervals) == [[1, 5]]


def test_ac2_contract_merge_touching_empty_unsorted():
    """AC2: Contract - half-open, sorted, touching merges, empty dropped, unsorted input."""
    intervals = [[1, 3], [3, 5], [5, 7], [2, 2], [0, 10]]
    assert merge(intervals) == [[0, 10]]


def test_ac3_implement_contract():
    """AC3: Implement the merge contract for the scheduler's interval logic."""
    intervals = [[1, 2], [2, 3], [3, 4], [4, 5]]
    assert merge(intervals) == [[1, 5]]
