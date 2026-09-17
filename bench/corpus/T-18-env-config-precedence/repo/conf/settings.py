"""Runtime settings.

Precedence (documented in the ops runbook): an environment variable always
overrides the built-in default. Variables are prefixed APP_ and upper-cased.
"""

import os

DEFAULTS = {"timeout": 30, "retries": 3, "verbose": "0"}


def get(key: str) -> str:
    if key in DEFAULTS:
        return DEFAULTS[key]
    return os.environ.get("APP_" + key.upper(), "")
