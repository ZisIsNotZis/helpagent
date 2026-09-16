"""Tests for restock picking."""

from inventory.pick import next_bin


def test_first_bin_is_picked():
    assert next_bin({"BIN-3": 4, "BIN-1": 9}) == "BIN-3"


def test_empty_stock_returns_sentinel():
    assert next_bin({}) == "NONE"
