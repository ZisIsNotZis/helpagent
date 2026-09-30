"""The timeout parameter must be threaded through every layer."""

import pytest

from api import client, transport
from api.service import sync_record
from exporter.bulk import export_all


def test_transport_accepts_timeout():
    assert transport.send("/u", "p", timeout=2.5) == "200:/u:p"


def test_client_threads_timeout(monkeypatch):
    seen = {}
    def fake_send(url, payload, timeout=1.0):
        seen["timeout"] = timeout
        return "ok"
    monkeypatch.setattr("api.client.send", fake_send)
    client.fetch("/u", timeout=7.5)
    assert seen["timeout"] == 7.5


def test_service_threads_timeout(monkeypatch):
    seen = {}
    def fake_fetch(url, payload="", timeout=1.0):
        seen["timeout"] = timeout
        return "ok"
    monkeypatch.setattr("api.service.fetch", fake_fetch)
    sync_record("r1", timeout=9.0)
    assert seen["timeout"] == 9.0


def test_exporter_threads_timeout(monkeypatch):
    seen = []
    def fake_fetch(url, payload="", timeout=1.0):
        seen.append(timeout)
        return "ok"
    monkeypatch.setattr("exporter.bulk.fetch", fake_fetch)
    export_all(["a", "b"], timeout=4.0)
    assert seen == [4.0, 4.0]
