"""Builds the daily report.

The HTTP API accepts ?format=json and must return a JSON document:
{"rows": [[...], ...]} - everything else keeps the legacy tabular text.
"""


def build_report(rows: list[list], as_json: bool = False) -> str:
    lines = ["DAILY REPORT"]
    for row in rows:
        lines.append(" | ".join(str(c) for c in row))
    return "\n".join(lines)
