# T-31-parameter-threading - solution (never shown to a run)

Three files: repo/api/transport.py (send gains `timeout: float = 1.0`), repo/api/client.py (fetch gains + threads it), repo/api/service.py and repo/exporter/bulk.py (both callers gain + thread it).

Red->green: all four chain tests fail before, pass after. Everything else stays byte-identical.
