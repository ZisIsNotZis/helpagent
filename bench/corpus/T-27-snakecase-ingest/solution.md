# T-27-snakecase-ingest - solution (never shown to a run)

One file: repo/ingest/records.py. normalize() must map the known camelCase keys to their snake_case names and drop everything else (a mapping dict + comprehension suffices; the four known keys are firstName/lastName/userId/createdAt).

Red->green: all three normalize tests fail before, pass after. Everything except repo/ingest/records.py stays byte-identical.
