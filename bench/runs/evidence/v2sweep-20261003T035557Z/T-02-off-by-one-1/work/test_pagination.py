"""Tests for catalog pagination off-by-one bug."""

from catalog.pagination import paginate, total_pages


def test_pagination_skips_last_item():
    items = list(range(1, 10))
    page = 1
    per_page = 4
    result = paginate(items, page, per_page)
    assert result == [1, 2, 3, 4]


def test_pagination_last_page_missing_last_item():
    items = list(range(1, 10))
    page = 2
    per_page = 4
    result = paginate(items, page, per_page)
    assert result == [5, 6, 7, 8]


def test_pagination_total_pages_undercounts():
    item_count = 10
    per_page = 4
    assert total_pages(item_count, per_page) == 3


def test_pagination_never_shows_missing_items():
    items = list(range(1, 10))
    page = 2
    per_page = 4
    result = paginate(items, page, per_page)
    assert all(item in items for item in result)
