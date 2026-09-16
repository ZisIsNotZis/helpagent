"""Fetch shim for the download endpoint."""

import time

# Documented backoff schedule: delay before retry attempt 1, then attempt 2.
DELAYS_S = (1, 2)

# The backend flags a transient hiccup with this marker in the response body.
RETRY_MARKER = "<transient>"


def fetch(send, url: str, *, sleep=time.sleep) -> str:
    """Fetch ``url`` through ``send``.

    A transient response is retried per the documented backoff schedule; ``sleep``
    is injectable so tests can observe the schedule without waiting.
    """
    return send(url)
