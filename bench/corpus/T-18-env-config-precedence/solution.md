# T-18-env-config-precedence — solution (never shown to a run)

One file: repo/conf/settings.py. get() returns DEFAULTS[key] whenever the key has a default, so the env var is never consulted — env must be checked first (None falls through to the default).

Red->green: test_env_overrides_default fails before, passes after; the default test passes throughout. Everything except repo/conf/settings.py stays byte-identical.
