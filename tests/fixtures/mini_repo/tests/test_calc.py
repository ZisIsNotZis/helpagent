"""Tests for minirepo.calc."""

import pytest

from minirepo.calc import divide
from minirepo.errors import MinirepoError


def test_divide_by_zero_raises_minirepo_error():
    """Conventions: built-in exceptions must never escape the public API."""
    with pytest.raises(MinirepoError):
        divide(1, 0)
