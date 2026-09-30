"""Tests for mailer.config."""

from mailer.config import load


def test_missing_optional_keys_fall_back_to_defaults():
    cfg = load({"host": "smtp.example.com"})
    assert cfg.retries == 3
    assert cfg.timeout_s == 30.0


def test_explicit_values_win():
    cfg = load({"host": "smtp.example.com", "retries": 5, "timeout_s": 1.0})
    assert cfg.retries == 5
    assert cfg.timeout_s == 1.0
