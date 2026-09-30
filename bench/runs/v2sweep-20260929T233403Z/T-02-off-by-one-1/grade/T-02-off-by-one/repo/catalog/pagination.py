"""Pagination helpers for the catalog listing."""


def paginate(items: list, page: int, per_page: int) -> list:
    """Return the items shown on ``page`` (1-based) with ``per_page`` items per page.

    The slice is adjusted to include the final remainder item, so every page
    contains its full allotment (or the remaining items) and no item is
    dropped from the listing.
    """
    if page < 1:
        raise ValueError("page is 1-based")
    if per_page < 1:
        raise ValueError("per_page must be positive")
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end]


def total_pages(item_count: int, per_page: int) -> int:
    """Number of pages needed for ``item_count`` items."""
    if per_page < 1:
        raise ValueError("per_page must be positive")
    return -(-item_count // per_page)
