"""Tests for the customer report export ordering."""

from reporting.export import export_rows


def test_rows_are_customer_ordered_case_insensitive_and_stable():
    """Rows must be ordered by customer, case-insensitively, stably.

    Customers that differ only by case keep their submitted order.
    """
    rows = [
        {"customer": "Zed", "total": 100.0},
        {"customer": "alice", "total": 200.0},
        {"customer": "Alice", "total": 300.0},
        {"customer": "zed", "total": 400.0},
    ]
    
    exported = export_rows(rows)
    
    expected = [
        ("alice", "200.00"),
        ("Alice", "300.00"),
        ("Zed", "100.00"),
        ("zed", "400.00"),
    ]
    
    assert exported == expected


def test_totals_are_formatted_with_two_decimals():
    rows = [{"customer": "Test", "total": 123.456}]
    
    exported = export_rows(rows)
    
    assert exported == [("Test", "123.46")]
