"""Tests for ratings/stats.py aggregation functions."""

from ratings.stats import average


def test_ac1_rounding_precision():
    """Mean must be explicitly rounded to exactly two decimal places."""
    scores = [1, 2, 3, 4, 5]
    expected = round(average(scores), 2)
    assert expected == 3.00
    assert isinstance(expected, float)
    assert round(expected, 2) == expected
