import pytest

from metrics.registry import Registry


def test_write_is_visible_to_the_next_read_after_increment():
    registry = Registry()
    registry.increment("active_users", by=10)
    assert registry.value("active_users") == 10
    registry.increment("active_users", by=5)
    assert registry.value("active_users") == 15


def test_write_is_visible_to_the_next_read_immediately():
    registry = Registry()
    registry.increment("active_users", by=10)
    assert registry.value("active_users") == 10
    registry.increment("active_users", by=10)
    assert registry.value("active_users") == 20
