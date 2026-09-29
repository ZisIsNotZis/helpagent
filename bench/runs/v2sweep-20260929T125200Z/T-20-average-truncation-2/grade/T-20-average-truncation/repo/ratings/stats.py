"""Aggregates for the review service."""


def average(scores: list[int]) -> float:
    """Mean of the given scores, rounded to 2 decimal places."""
    return round(sum(scores), 2)