"""Precedence tests."""

import pytest

from conf import settings


def test_env_overrides_default(monkeypatch):
    monkeypatch.setenv("APP_TIMEOUT", "5")
    assert settings.get("timeout") == "5"


def test_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("APP_RETRIES", raising=False)
    assert settings.get("retries") == 3
