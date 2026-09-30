"""Registry contract (see the design doc)."""

import pytest

from plugins import registry


def test_register_and_get():
    registry.register("greet", lambda: "hi")
    assert registry.get("greet")() == "hi"


def test_get_unknown_raises():
    with pytest.raises(KeyError):
        registry.get("nope")


def test_register_duplicate_rejected():
    registry.register("dup", lambda: 1)
    with pytest.raises(ValueError):
        registry.register("dup", lambda: 2)


def test_run_passes_args():
    registry.register("add", lambda a, b: a + b)
    assert registry.run("add", 2, 3) == 5
