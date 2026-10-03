"""Tests for configurable timeouts end to end."""

import pytest

from api.client import fetch
from api.transport import send


def test_send_accepts_timeout_parameter():
    result = send("/test", "payload", timeout=2.0)
    assert result == "200:/test:payload"


def test_fetch_threads_timeout_parameter():
    result = fetch("/test", "payload", timeout=2.0)
    assert result == "200:/test:payload"


def test_existing_callers_without_timeout_still_work():
    result = send("/test", "payload")
    assert result == "200:/test:payload"

    result = fetch("/test", "payload")
    assert result == "200:/test:payload"
