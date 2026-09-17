# T-30-naive-datetime-compare - solution (never shown to a run)

One file: repo/tokens/tokens.py. is_expired() must normalize a naive `at` to UTC (replace(tzinfo=timezone.utc)) before comparing; issue() stays untouched.

Red->green: an expired-check with a naive input fails before, passes after. Everything except repo/tokens/tokens.py stays byte-identical.
