"""Tests for the job scheduler."""

from datetime import datetime, timezone

from scheduler.jobs import is_due


def _utc(y: int, mo: int, d: int, h: int) -> datetime:
    return datetime(y, mo, d, h, tzinfo=timezone.utc)


def test_job_not_due_before_next_run():
    job = {"next_run": _utc(2099, 1, 1, 9)}
    assert not is_due(job, now=_utc(2025, 1, 1, 9))


def test_due_check_works_with_the_default_clock():
    job = {"next_run": _utc(2099, 1, 1, 9)}
    assert not is_due(job)
