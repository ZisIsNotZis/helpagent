"""Average tests (the API returns floats)."""

from ratings.stats import average


def test_half_star_average():
    assert average([4, 5]) == 4.5


def test_repeating_fraction_rounds():
    assert average([1, 2, 2]) == 1.67
