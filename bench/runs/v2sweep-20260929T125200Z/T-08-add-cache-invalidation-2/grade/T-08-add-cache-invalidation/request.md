Our metrics dashboard keeps showing stale numbers until the process restarts — we
increment counters from the API and the dashboard's reads just don't move. The registry
was built with a read cache for speed and that part is fine, but a write has to be
visible to the very next read, always. Please fix it.
