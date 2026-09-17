# T-17-log-hour-format — solution (never shown to a run)

One file: repo/logparse/parser.py. The strptime pattern uses %I (12-hour clock) without %p — the service logs 24-hour time, so the directive must be %H.

Red->green: test_afternoon_hour_is_parse fails before, passes after; morning test passes throughout. Everything except repo/logparse/parser.py stays byte-identical.
