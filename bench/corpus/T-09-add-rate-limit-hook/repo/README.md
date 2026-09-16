# throttle — per-key limiter

Allows up to ``threshold`` hits per key, then blocks. ``on_limit`` is an optional
callback invoked as ``on_limit(key)``: it fires once per key, when the key first
crosses the threshold; later blocked hits do not re-fire it. ``None`` disables it.

Run the tests: `python -m pytest`
