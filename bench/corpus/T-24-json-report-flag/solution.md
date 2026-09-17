# T-24-json-report-flag - solution (never shown to a run)

One file: repo/report/builder.py. build_report ignores its as_json flag; when true it must return json.dumps({"rows": rows}) and otherwise keep the legacy path untouched.

Red->green: test_json_mode_returns_document fails before, passes after; the text-mode test passes throughout. Everything except repo/report/builder.py stays byte-identical.
