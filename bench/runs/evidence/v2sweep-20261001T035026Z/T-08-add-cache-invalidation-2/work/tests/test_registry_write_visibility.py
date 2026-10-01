"""Regression test: a write must be visible to the very next read, always."""

from metrics.registry import Registry


def test_write_is_visible_to_the_next_read():
    registry = Registry()
    registry.increment("active_users", by=10)
    assert registry.value("active_users") == 10


def test_write_is_visible_to_the_next_read_after_multiple_writes():
    registry = Registry()
    registry.increment("active_users", by=10)
    registry.increment("active_users", by=5)
    assert registry.value("active_users") == 15


def test_write_is_visible_to_the_next_read_with_fresh_counter():
    registry = Registry()
    registry.increment("new_counter", by=20)
    assert registry.value("new_counter") == 20


def test_write_is_visible_to_the_next_read_with_cache_preserved():
    registry = Registry()
    registry.increment("active_users", by=10)
    assert registry.value("active_users") == 10
    registry.increment("active_users", by=5)
    assert registry.value("active_users") == 15
    assert registry.value("active_users") == 15
