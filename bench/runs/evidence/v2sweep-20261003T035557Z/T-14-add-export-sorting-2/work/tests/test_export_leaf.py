"""Tests for the customer report export ordering."""

from reporting.export import export_rows


def test_rows_are_customer_ordered_case_insensitive_and_stable():
    """Rows must be ordered by customer, case-insensitively, stably.

    The docs promise customers in alphabetical order ignoring case, and when two
    customers differ only by case the earlier submission should come first.
    """
    rows = [
        {"customer": "Zed", "total": 100.0},
        {"customer": "alice", "total": 200.0},
        {"customer": "Alice", "total": 300.0},
        {"customer": "bob", "total": 400.0},
    ]

    result = export_rows(rows)

    expected_customers = ["alice", "Alice", "bob", "Zed"]
    assert [row[0] for row in result] == expected_customers
    assert [row[1] for row in result] == ["200.00", "300.00", "400.00", "100.00"]


def test_totals_are_formatted_with_two_decimals():
    rows = [{"customer": "alice", "total": 123.456789}]
    result = export_rows(rows)
    assert result == [("alice", "123.46")]
