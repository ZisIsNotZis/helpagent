"""Tests for the customer report export ordering."""

from reporting.export import export_rows


def test_rows_are_customer_ordered_case_insensitive_and_stable():
    """Rows must be sorted by customer case-insensitively, stable.

    Customers that differ only by case keep their submitted order.
    """
    rows = [
        {"customer": "Zed", "total": 100.0},
        {"customer": "alice", "total": 200.0},
        {"customer": "Bob", "total": 300.0},
        {"customer": "bob", "total": 400.0},
        {"customer": "Alice", "total": 500.0},
    ]

    result = export_rows(rows)

    expected = [
        ("alice", "200.00"),
        ("Bob", "300.00"),
        ("bob", "400.00"),
        ("Zed", "100.00"),
        ("Alice", "500.00"),
    ]

    assert result == expected
