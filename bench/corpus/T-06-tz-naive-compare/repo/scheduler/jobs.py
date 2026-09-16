"""Background job scheduling.

All timestamps in this module are timezone-aware UTC.
"""

from datetime import datetime, timedelta, timezone

RUN_INTERVAL = timedelta(minutes=15)


def next_run(after: datetime) -> datetime:
    """Next run strictly after ``after``."""
    return after + RUN_INTERVAL


def is_due(job: dict, now: datetime | None = None) -> bool:
    """True when ``job``'s next_run has passed at ``now`` (UTC now by default)."""
    now = now or datetime.utcnow()
    return job["next_run"] <= now
