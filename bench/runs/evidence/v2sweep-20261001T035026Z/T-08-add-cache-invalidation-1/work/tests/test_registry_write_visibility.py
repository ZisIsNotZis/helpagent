"""Test that a write is visible to the very next read, even without a restart."""

from metrics.registry import Registry


def test_write_is_visible_to_the_next_read_without_restart():
    registry = Registry()
    registry.increment("requests", by=10)
    assert registry.value("requests") == 10
    registry.increment("requests", by=5)
    assert registry.value("requests") == 15
    registry.increment("requests", by=2)
    assert registry.value("requests") == 17
