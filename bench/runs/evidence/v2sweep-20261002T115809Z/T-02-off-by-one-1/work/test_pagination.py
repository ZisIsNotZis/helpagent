"""Tests for catalog pagination behavior."""

from catalog.pagination import paginate, total_pages


def test_pagination_slices_off_by_one():
    items = list(range(10))
    page = 1
    per_page = 4

    result = paginate(items, page, per_page)

    # With 4 per page, page 1 should show exactly 4 items, not 3.
    assert len(result) == 4
    assert result == [0, 1, 2, 3]


def test_last_page_missing_last_item():
    items = list(range(10))
    page = 3
    per_page = 4

    result = paginate(items, page, per_page)

    # Page 3 should hold the remainder (2 items), not 3.
    assert len(result) == 2
    assert result == [8, 9]


def test_total_pages_correct():
    item_count = 10
    per_page = 4

    assert total_pages(item_count, per_page) == 3


def test_some_products_never_show_up():
    items = list(range(10))
    page = 2
    per_page = 4

    result = paginate(items, page, per_page)

    # Page 2 should show items 4, 5, 6, 7.
    assert result == [4, 5, 6, 7]
    assert 8 not in result
    assert 9 not in result
