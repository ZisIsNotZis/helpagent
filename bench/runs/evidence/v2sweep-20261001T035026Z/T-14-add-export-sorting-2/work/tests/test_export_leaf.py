"""Tests for the customer report export ordering.

The exported report must place rows by customer in alphabetical order,
ignoring case, with stable order for case-only differences.
"""

from reporting.export import export_rows


def test_rows_are_customer_ordered_case_insensitive_and_stable():
    """Rows are ordered case-insensitively and stable for case-only ties."""
    rows = [
        {"customer": "Zebra", "total": 100.0},
        {"customer": "apple", "total": 200.0},
        {"customer": "Apple", "total": 300.0},
        {"customer": "banana", "total": 400.0},
    ]
    exported = export_rows(rows)
    expected = [
        ("apple", "200.00"),
        ("Apple", "300.00"),
        ("banana", "400.00"),
        ("Zebra", "100.00"),
    ]
    assert exported == expected
