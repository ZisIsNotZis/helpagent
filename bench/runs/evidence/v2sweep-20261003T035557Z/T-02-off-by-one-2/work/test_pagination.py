"""Tests for catalog pagination off-by-one bug."""

from catalog.pagination import paginate, total_pages


def test_pagination_skips_last_item():
    items = list(range(1, 10))
    page = 1
    per_page = 4

    result = paginate(items, page, per_page)

    # With 4 per page, page 1 should show items 1-4, not 1-3.
    assert result == [1, 2, 3, 4]


def test_pagination_missing_last_item():
    items = list(range(1, 10))
    page = 2
    per_page = 4

    result = paginate(items, page, per_page)

    # Page 2 should show items 5-8, not 5-7.
    assert result == [5, 6, 7, 8]


def test_pagination_last_page_missing_last_item():
    items = list(range(1, 10))
    page = 3
    per_page = 4

    result = paginate(items, page, per_page)

    # With 10 items and 4 per page, there are 3 pages.
    # Page 3 should only have 2 items (9, 10), not 3.
    assert result == [9, 10]


def test_pagination_total_pages_correct():
    item_count = 10
    per_page = 4

    assert total_pages(item_count, per_page) == 3


def test_pagination_some_products_never_show():
    items = list(range(1, 10))
    page = 1
    per_page = 4

    result = paginate(items, page, per_page)

    # The last two items should never appear on page 1.
    assert 9 not in result
    assert 10 not in result
