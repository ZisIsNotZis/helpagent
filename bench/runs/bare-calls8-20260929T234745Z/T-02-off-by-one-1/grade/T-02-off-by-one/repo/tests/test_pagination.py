"""Tests for catalog.pagination."""

from catalog.pagination import paginate, total_pages

ITEMS = list(range(10))


def test_first_page_returns_per_page_items():
    assert paginate(ITEMS, 1, 4) == [0, 1, 2, 3]


def test_last_page_returns_remainder():
    assert paginate(ITEMS, 3, 4) == [8, 9]


def test_consecutive_pages_are_contiguous():
    assert paginate(ITEMS, 1, 4) + paginate(ITEMS, 2, 4) == ITEMS[:8]


def test_total_pages_rounds_up():
    assert total_pages(10, 4) == 3
