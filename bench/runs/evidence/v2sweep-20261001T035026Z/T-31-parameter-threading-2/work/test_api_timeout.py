"""Tests for configurable timeouts end to end."""

import pytest

from api.transport import send
from api.client import fetch
from api.service import sync_record
from exporter.bulk import export_all


def test_send_accepts_timeout_parameter():
    result = send("/test", "payload", timeout=2.0)
    assert result == "200:/test:payload"


def test_fetch_threads_timeout():
    result = fetch("/test", "payload", timeout=3.0)
    assert result == "200:/test:payload"


def test_sync_record_passes_timeout():
    result = sync_record("123", timeout=2.0)
    assert result == "200:/records/123:sync"


def test_export_all_passes_timeout():
    result = export_all([1, 2], timeout=2.0)
    assert result == ["200:/export/1:" , "200:/export/2:" ]


def test_default_timeout_is_one():
    result = send("/test", "payload")
    assert result == "200:/test:payload"
