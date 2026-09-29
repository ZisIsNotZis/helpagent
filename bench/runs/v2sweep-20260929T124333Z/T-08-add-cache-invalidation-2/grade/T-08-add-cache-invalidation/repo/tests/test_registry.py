"""Tests for the counters registry."""

from metrics.registry import Registry


def test_fresh_counter_starts_at_zero():
    r = Registry()
    assert r.value("hits") == 0


def test_write_is_visible_to_the_next_read():
    r = Registry()
    r.increment("hits")
    assert r.value("hits") == 1
    r.increment("hits", by=4)
    assert r.value("hits") == 5
