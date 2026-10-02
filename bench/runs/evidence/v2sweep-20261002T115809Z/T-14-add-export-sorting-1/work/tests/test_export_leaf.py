"""Tests for the customer report export ordering.

The exported report must honor the documented order: customers are sorted
case-insensitively, and ties keep the submitted order (stable sort).
"""

from reporting.export import export_rows


def test_rows_are_customer_ordered_case_insensitive_and_stable():
    """Rows are ordered by customer, case-insensitively and stably.

    Customers that differ only by case keep their submitted order.
    """
    rows = [
        {"customer": "Zebra", "total": 100.0},
        {"customer": "apple", "total": 200.0},
        {"customer": "Apple", "total": 300.0},
        {"customer": "banana", "total": 400.0},
    ]
    
    exported = export_rows(rows)
    
    expected_customers = ["apple", "Apple", "banana", "Zebra"]
    
    assert [row[0] for row in exported] == expected_customers
    assert [row[1] for row in exported] == ["200.00", "300.00", "400.00", "100.00"]
