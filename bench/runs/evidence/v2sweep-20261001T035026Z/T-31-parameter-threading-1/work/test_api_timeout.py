"""Tests for configurable timeouts end to end."""

import pytest

from api.transport import send
from api.client import fetch


def test_send_accepts_timeout_parameter():
    result = send("/test", "payload", timeout=0.5)
    assert result == "200:/test:payload"


def test_fetch_accepts_timeout_parameter():
    result = fetch("/test", "payload", timeout=0.5)
    assert result == "200:/test:payload"


def test_existing_callers_without_timeout_still_work():
    result = send("/test", "payload")
    assert result == "200:/test:payload"

    result = fetch("/test", "payload")
    assert result == "200:/test:payload"


def test_bulk_exporter_passes_timeout():
    from exporter.bulk import export_all

    result = export_all(["1", "2"], timeout=0.5)
    assert result == ["200:/export/1:" , "200:/export/2:" ]
