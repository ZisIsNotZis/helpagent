# fetcher

Tiny fetch shim for the download endpoint.

A transient backend response (marked in the body) is retried per the documented
backoff schedule — `DELAYS_S` = (1, 2): one second before the first retry, two
before the second. `sleep` is injectable, so tests observe the schedule without
waiting. If every attempt comes back transient, the marker is returned to the
caller.

Run the tests: `python -m pytest`
