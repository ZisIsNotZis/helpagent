import pytest
from spans.merge import merge


def test_ac1_overlapping_merged():
    """AC1: Overlapping spans must be merged, not left separate."""
    intervals = [[1, 4), [2, 5), [3, 6)]
    result = merge(intervals)
    assert result == [[1, 6)]


def test_ac2_contract_merge_touching_drop_empty():
    """AC2: Half-open, sorted, touching merges, empty dropped, unsorted input."""
    intervals = [[1, 3), [3, 5), [2, 4), [], [5, 7)]
    result = merge(intervals)
    assert result == [[1, 5), [5, 7)]


def test_ac3_contract_implementation():
    """AC3: The scheduler's interval merge is implemented to the contract."""
    intervals = [[1, 2), [2, 3), [3, 4), [4, 5)]
    result = merge(intervals)
    assert result == [[1, 5)]
