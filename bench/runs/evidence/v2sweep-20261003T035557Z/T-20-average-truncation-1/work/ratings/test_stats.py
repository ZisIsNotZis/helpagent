"""Tests for the ratings stats module."""

from ratings.stats import average


def test_average_rounds_to_two_decimals():
    """Mean must be rounded to 2 decimal places."""
    scores = [4, 5, 4, 5]
    assert average(scores) == 4.50


def test_average_includes_half_star_items():
    """Every product rated 4 stars, including 4.5-star items."""
    scores = [4, 4.5, 4, 4]
    assert average(scores) == 4.375
