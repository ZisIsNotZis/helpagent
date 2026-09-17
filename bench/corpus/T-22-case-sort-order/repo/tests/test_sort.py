"""Sorting tests (handbook: case-insensitive alphabetical)."""

from roster.sort import sorted_names


def test_mixed_case_order():
    assert sorted_names(["alice", "Zoe", "Bob"]) == ["alice", "Bob", "Zoe"]


def test_stability_for_same_name():
    assert sorted_names(["amy", "AMY"]) == ["amy", "AMY"]
