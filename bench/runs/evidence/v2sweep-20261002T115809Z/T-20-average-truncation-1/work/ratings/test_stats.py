"""Tests for the ratings stats module."""

from ratings.stats import average


def test_average_rounds_to_two_decimals():
    # Mean is 4.5, must be rounded to 4.50 (float), not truncated to 4.
    scores = [4, 5, 4, 5, 4, 5, 4, 5, 4, 5]
    assert average(scores) == 4.5


def test_average_handles_4_5_star_items():
    # Must show every product rated 4 stars, even 4.5-star items.
    scores = [4, 4, 4, 4, 4, 4, 4, 4, 4, 4.5]
    assert average(scores) == 4.5
