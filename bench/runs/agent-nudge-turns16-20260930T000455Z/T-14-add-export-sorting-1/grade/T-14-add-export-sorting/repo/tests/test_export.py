"""Tests for the report export."""

from reporting.export import export_rows


ROWS = [
    {"customer": "northwind", "total": 5},
    {"customer": "Acme", "total": 3},
    {"customer": "ACME corp", "total": 9},
    {"customer": "acme corp", "total": 2},
    {"customer": "Borealis", "total": 1},
]


def test_rows_are_customer_ordered_case_insensitive_and_stable():
    out = export_rows(ROWS)
    assert [r[0] for r in out] == ["Acme", "ACME corp", "acme corp", "Borealis", "northwind"]


def test_totals_are_formatted_with_two_decimals():
    out = export_rows([{"customer": "a", "total": 7}])
    assert out == [("a", "7.00")]
