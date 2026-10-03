"""Tests for the customer report export ordering behavior."""

from reporting.export import export_rows


def test_rows_are_customer_ordered_case_insensitive_and_stable():
    """Rows must be ordered by customer, case-insensitively, stably.

    Customers are sorted ignoring case; when two customers differ only by case,
    the earlier submission must come first (stable sort).
    """
    rows = [
        {"customer": "Zed", "total": 100.0},
        {"customer": "alice", "total": 200.0},
        {"customer": "Alice", "total": 300.0},
        {"customer": "bob", "total": 400.0},
    ]
    
    exported = export_rows(rows)
    
    expected_customers = ["alice", "Bob", "Zed", "Alice"]
    
    assert [row[0] for row in exported] == expected_customers
    assert [row[1] for row in exported] == ["200.00", "400.00", "100.00", "300.00"]
