from catalog.pagination import paginate, total_pages

def test_pagination_first_page_full():
    items = list(range(1, 11))
    page = 1
    per_page = 4

    result = paginate(items, page, per_page)

    # Page 1 must show exactly 4 items, not 3.
    assert len(result) == 4
    assert result == [1, 2, 3, 4]

def test_pagination_last_page_full():
    items = list(range(1, 11))
    page = 3
    per_page = 4

    result = paginate(items, page, per_page)

    # Page 3 must show exactly 2 items, not 3.
    assert len(result) == 2
    assert result == [9, 10]

def test_pagination_all_items_shown():
    items = list(range(1, 11))
    page = 1
    per_page = 4

    result = paginate(items, page, per_page)

    # No item should be missing from the listing due to the off-by-one.
    assert set(result) == {1, 2, 3, 4}

def test_total_pages_correct():
    item_count = 10
    per_page = 4

    pages = total_pages(item_count, per_page)

    # 10 items with 4 per page should need exactly 3 pages.
    assert pages == 3
