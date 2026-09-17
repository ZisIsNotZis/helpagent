"""Timestamp parsing tests (24-hour service log)."""

from datetime import datetime

from logparse.parser import parse_ts


def test_afternoon_hour_is_parse():
    ts = parse_ts("[2025-06-01 14:30:00] INFO boot ok")
    assert ts == datetime(2025, 6, 1, 14, 30, 0)


def test_morning_hour_unchanged():
    ts = parse_ts("[2025-06-01 09:15:00] WARN slow disk")
    assert ts == datetime(2025, 6, 1, 9, 15, 0)
