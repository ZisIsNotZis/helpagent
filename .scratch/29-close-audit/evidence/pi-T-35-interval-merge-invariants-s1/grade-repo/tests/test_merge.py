"""Merge contract tests (half-open semantics)."""

from spans.merge import merge


def test_unsorted_input_sorted_output():
    assert merge([(5, 9), (1, 3)]) == [(1, 3), (5, 9)]


def test_overlapping_merge():
    assert merge([(1, 4), (2, 6)]) == [(1, 6)]


def test_touching_merge():
    assert merge([(1, 3), (3, 5)]) == [(1, 5)]


def test_empty_intervals_dropped():
    assert merge([(2, 2), (1, 3)]) == [(1, 3)]


def test_gap_preserved():
    assert merge([(1, 2), (4, 6)]) == [(1, 2), (4, 6)]


def test_chain_of_touching():
    assert merge([(0, 1), (1, 2), (2, 3), (5, 6)]) == [(0, 3), (5, 6)]
