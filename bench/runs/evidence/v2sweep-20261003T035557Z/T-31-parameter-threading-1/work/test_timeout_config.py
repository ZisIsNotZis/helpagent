"""Tests for configurable timeouts end to end."""

import pytest

from api.transport import send
from api.client import fetch


def test_send_accepts_timeout_parameter():
    result = send("/test", "payload", timeout=0.5)
    assert result == "200:/test:payload"


def test_fetch_threads_timeout():
    result = fetch("/test", "payload", timeout=0.5)
    assert result == "200:/test:payload"


def test_callers_can_pass_own_timeout():
    from api.service import sync_record
    from exporter.bulk import export_all

    assert sync_record("123", timeout=0.5) == "200:/records/123:sync"
    assert export_all(["123"], timeout=0.5) == ["200:/export/123"]


def test_existing_callers_without_timeout_still_work():
    result = send("/test", "payload")
    assert result == "200:/test:payload"

    result = fetch("/test", "payload")
    assert result == "200:/test:payload"

    assert sync_record("123") == "200:/records/123:sync"

    assert export_all(["123"]) == ["200:/export/123"]
