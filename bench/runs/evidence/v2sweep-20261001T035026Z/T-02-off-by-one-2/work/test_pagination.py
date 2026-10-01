"""Tests for catalog pagination off-by-one bug."""

from catalog.pagination import paginate, total_pages


def test_pagination_skips_last_item():
    items = list(range(1, 10))
    page = 1
    per_page = 4
    result = paginate(items, page, per_page)
    assert result == [1, 2, 3, 4]


def test_pagination_missing_last_item():
    items = list(range(1, 10))
    page = 2
    per_page = 4
    result = paginate(items, page, per_page)
    assert result == [5, 6, 7, 8]


def test_pagination_last_page_missing_last_item():
    items = list(range(1, 10))
    page = 3
    per_page = 4
    result = paginate(items, page, per_page)
    assert result == [9]


def test_pagination_total_pages_mismatch():
    assert total_pages(10, 4) == 3


def test_pagination_never_shows_all_items():
    items = list(range(1, 10))
    page = 1
    per_page = 4
    result = paginate(items, page, per_page)
    assert len(result) == 3
    assert result[-1] != 4
    assert 4 not in result
